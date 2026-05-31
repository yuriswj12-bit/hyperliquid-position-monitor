import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.hyperliquid import HyperliquidClient
from app.models import HyperliquidStateRequest
from app.notifier import TelegramNotifier
from app.risk import liquidation_alerts, normalize_snapshot
from app.storage import Storage

settings = get_settings()
storage = Storage(settings.database_path)
client = HyperliquidClient(settings)
notifier = TelegramNotifier(settings)
PUBLIC_DIR = Path("public").resolve()


async def monitor_loop() -> None:
    while True:
        for wallet in settings.watched_wallets:
            try:
                raw = await client.clearinghouse_state(wallet)
                snapshot = normalize_snapshot(wallet, raw, settings.liquidation_alert_percent)
                alerts = liquidation_alerts(snapshot)
                await storage.save_snapshot(snapshot)
                await storage.save_alerts(alerts)
                await notifier.send_alerts(alerts)
            except Exception as error:
                print(f"monitor error for {wallet}: {error}")
        await asyncio.sleep(settings.monitor_interval_seconds)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.init()
    task = asyncio.create_task(monitor_loop()) if settings.watched_wallets else None
    yield
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
        raw = await client.clearinghouse_state(request.user, request.endpoint, request.dex)
        snapshot = normalize_snapshot(request.user, raw, settings.liquidation_alert_percent)
        alerts = liquidation_alerts(snapshot)
        await storage.save_snapshot(snapshot)
        await storage.save_alerts(alerts)
        await notifier.send_alerts(alerts)
        return snapshot.model_dump(mode="json")
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.get("/api/alerts")
async def alerts(limit: int = 50) -> list[dict]:
    return await storage.recent_alerts(limit)


app.mount("/assets", StaticFiles(directory="public"), name="assets")


@app.get("/{path:path}")
async def web_app(path: str) -> FileResponse:
    if path and "." in path:
        requested = (PUBLIC_DIR / path).resolve()
        if requested.is_file() and PUBLIC_DIR in requested.parents:
            return FileResponse(requested, headers={"cache-control": "no-store"})
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse("public/index.html", headers={"cache-control": "no-store"})
