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
from app.models import HyperliquidStateRequest, WalletRequest, WatchedWalletRequest
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


ai_analyst = AIAnalyst(settings, storage, process_wallet_state)
command_bot = TelegramCommandBot(settings, storage, process_wallet_state, ai_analyst)


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


@app.get("/api/alerts")
async def alerts(limit: int = 50) -> list[dict]:
    return await storage.recent_alerts(limit)


@app.get("/api/position-changes")
async def changes(limit: int = 50) -> list[dict]:
    return await storage.recent_position_changes(limit)


@app.get("/api/watched-wallets")
async def watched_wallets() -> list[dict]:
    return await storage.list_watched_wallets()


@app.post("/api/watched-wallets")
async def upsert_watched_wallet(request: WatchedWalletRequest) -> dict:
    return await storage.upsert_watched_wallet(request)


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
