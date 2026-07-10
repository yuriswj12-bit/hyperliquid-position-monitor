from typing import Any

import httpx

from app.config import Settings


class HyperliquidClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def clearinghouse_state(
        self,
        user: str,
        endpoint: str | None = None,
        dex: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": "clearinghouseState", "user": user}
        if dex:
            payload["dex"] = dex

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(endpoint or self.settings.hyperliquid_info_url, json=payload)
            response.raise_for_status()
            return response.json()

    async def user_fills(
        self,
        user: str,
        endpoint: str | None = None,
        aggregate_by_time: bool = True,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "type": "userFills",
            "user": user,
            "aggregateByTime": aggregate_by_time,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(endpoint or self.settings.hyperliquid_info_url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
