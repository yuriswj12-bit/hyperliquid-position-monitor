import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai_analyst import AIAnalyst
from app.config import get_settings
from app.hyperliquid import HyperliquidClient
from app.models import HyperliquidFillsRequest, HyperliquidStateRequest, WalletRequest, WatchedWalletRequest
from app.notifier import TelegramNotifier
from app.risk import liquidation_alerts, normalize_snapshot, position_changes
from app.storage import Storage
from app.telegram_bot import TelegramCommandBot

settings = get_settings()
storage = Storage(settings.database_path)
client = HyperliquidClient(settings)
notifier = TelegramNotifier(settings)
PUBLIC_DIR = Path("public").resolve()


async def process_wallet_state(user: str, endpoint: str | None = None, dex: str | None = None) -> dict:
    raw = await client.clearinghouse_state(user, endpoint, dex)
    previous = await storage.latest_snapshot(user, settings.liquidation_alert_percent)
    snapshot = normalize_snapshot(user, raw, settings.liquidation_alert_percent)
    changes = position_changes(previous, snapshot, settings.position_change_alert_percent)
    alerts = await storage.filter_alerts_for_cooldown(
        liquidation_alerts(snapshot),
        settings.alert_cooldown_seconds,
    )

    await storage.save_snapshot(snapshot)
    await storage.save_position_changes(changes)
    await storage.save_alerts(alerts)
    await notifier.send_alerts(alerts)

    return {
        "snapshot": snapshot.model_dump(mode="json"),
        "changes": [change.model_dump(mode="json") for change in changes],
        "alerts": [alert.model_dump(mode="json") for alert in alerts],
    }


async def process_wallet_fills(user: str, endpoint: str | None = None, aggregate_by_time: bool = True) -> dict:
    fills = await client.user_fills(user, endpoint, aggregate_by_time)
    saved_count = await storage.save_fills(user, fills)
    return {
        "user": user,
        "fetched_count": len(fills),
        "saved_count": saved_count,
        "fills": fills[:50],
    }


async def refresh_active_wallets() -> dict:
    wallets = await storage.active_wallet_addresses(settings.watched_wallets)
    results = []
    for wallet in wallets:
        try:
            result = await process_wallet_state(wallet)
            fills_result = await process_wallet_fills(wallet)
            results.append(
                {
                    "user": wallet,
                    "ok": True,
                    "positions": len(result["snapshot"].get("positions", [])),
                    "changes": len(result["changes"]),
                    "alerts": len(result["alerts"]),
                    "fills_saved": fills_result["saved_count"],
                }
            )
        except Exception as error:
            results.append({"user": wallet, "ok": False, "error": str(error)})
    return {
        "wallet_count": len(wallets),
        "success_count": sum(1 for result in results if result["ok"]),
        "failure_count": sum(1 for result in results if not result["ok"]),
        "results": results,
    }


ai_analyst = AIAnalyst(settings, storage, process_wallet_state, process_wallet_fills)
command_bot = TelegramCommandBot(settings, storage, process_wallet_state, process_wallet_fills, ai_analyst)


async def monitor_loop() -> None:
    while True:
        for wallet in await storage.active_wallet_addresses(settings.watched_wallets):
            try:
                await process_wallet_state(wallet)
            except Exception as error:
                print(f"monitor error for {wallet}: {error}")
        await asyncio.sleep(settings.monitor_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.init()
    task = asyncio.create_task(monitor_loop())
    await command_bot.start()
    yield
    await command_bot.stop()
    if task:
        task.cancel()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "app": settings.app_name}


@app.post("/api/info")
async def info_proxy(request: HyperliquidStateRequest) -> dict:
    try:
        return await client.clearinghouse_state(request.user, request.endpoint, request.dex)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/state")
async def state(request: HyperliquidStateRequest) -> dict:
    try:
        return await process_wallet_state(request.user, request.endpoint, request.dex)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/fills")
async def fills_proxy(request: HyperliquidFillsRequest) -> dict:
    try:
        return await process_wallet_fills(request.user, request.endpoint, request.aggregate_by_time)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/alerts")
async def alerts(limit: int = 50) -> list[dict]:
    return await storage.recent_alerts(limit)


@app.get("/api/position-changes")
async def changes(limit: int = 50) -> list[dict]:
    return await storage.recent_position_changes(limit)


@app.get("/api/fills")
async def recent_fills(user: str | None = None, limit: int = 50) -> list[dict]:
    if user:
        request = WalletRequest(user=user)
        return await storage.recent_fills(request.user, limit)
    return await storage.recent_fills(None, limit)


@app.get("/api/wallets/{user}/summary")
async def wallet_summary(user: str, hours: int = 24) -> dict:
    request = WalletRequest(user=user)
    return await storage.wallet_summary(request.user, hours)


@app.get("/api/wallets/{user}/position-changes")
async def wallet_position_changes(user: str, limit: int = 20) -> list[dict]:
    request = WalletRequest(user=user)
    return await storage.wallet_position_changes(request.user, limit)


@app.get("/api/watched-wallets")
async def watched_wallets() -> list[dict]:
    return await storage.list_watched_wallets()


@app.post("/api/watched-wallets")
async def upsert_watched_wallet(request: WatchedWalletRequest) -> dict:
    return await storage.upsert_watched_wallet(request)


@app.post("/api/watched-wallets/refresh")
async def refresh_watched_wallets() -> dict:
    return await refresh_active_wallets()


@app.delete("/api/watched-wallets/{user}")
async def delete_watched_wallet(user: str) -> dict:
    request = WalletRequest(user=user)
    deleted = await storage.delete_watched_wallet(request.user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Wallet is not in the watchlist")
    return {"deleted": True, "user": request.user}


app.mount("/assets", StaticFiles(directory="public"), name="assets")


@app.get("/{path:path}")
async def web_app(path: str) -> FileResponse:
    if path and "." in path:
        requested = (PUBLIC_DIR / path).resolve()
        if requested.is_file() and PUBLIC_DIR in requested.parents:
            return FileResponse(requested, headers={"cache-control": "no-store"})
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse("public/index.html", headers={"cache-control": "no-store"})
