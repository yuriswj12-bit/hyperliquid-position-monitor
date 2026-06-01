import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.config import Settings
from app.models import AccountSnapshot
from app.storage import Storage

RefreshCallback = Callable[[str], Awaitable[dict]]


class AIAnalyst:
    def __init__(self, settings: Settings, storage: Storage, refresh_callback: RefreshCallback) -> None:
        self.settings = settings
        self.storage = storage
        self.refresh_callback = refresh_callback

    @property
    def enabled(self) -> bool:
        return self.settings.ai_provider.lower() == "groq" and bool(self.settings.groq_api_key)

    async def answer(self, user_text: str) -> str | None:
        if not self.enabled:
            return None

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are Hyperdress.AI, a concise Hyperliquid position monitoring analyst. "
                    "Answer in Chinese when the user writes Chinese; otherwise answer in the user's language. "
                    "Use tools before answering factual monitor questions. Do not invent wallet data. "
                    "For alert/risk questions, call get_recent_alerts. "
                    "For position-change questions, call get_recent_changes. "
                    "For largest/top wallet questions, call get_top_wallet_by_position_value. "
                    "For position questions with a wallet address, call refresh_wallet_state. "
                    "For position questions without a wallet address, call get_latest_positions. "
                    "If the relevant tool returns no data, say that clearly and tell the user the next action."
                ),
            },
            {"role": "user", "content": user_text},
        ]

        first = await self.chat(messages, tools=TOOL_SCHEMAS)
        message = first["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return message.get("content")

        messages.append(message)
        for tool_call in tool_calls:
            function = tool_call["function"]
            name = function["name"]
            try:
                arguments = json.loads(function.get("arguments") or "{}")
                result = await self.run_tool(name, arguments)
            except Exception as error:
                result = {"error": str(error)}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        final = await self.chat(messages)
        return final["choices"][0]["message"].get("content")

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict:
        payload: dict[str, Any] = {
            "model": self.settings.groq_model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        proxy = self.settings.ai_proxy_url or self.settings.telegram_proxy_url
        async with httpx.AsyncClient(timeout=45, proxy=proxy) as client:
            response = await client.post(
                f"{self.settings.groq_base_url.rstrip('/')}/chat/completions",
                headers={
                    "authorization": f"Bearer {self.settings.groq_api_key}",
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def run_tool(self, name: str, arguments: dict[str, Any]) -> dict:
        if name == "get_recent_alerts":
            return {"alerts": await self.storage.recent_alerts(limit_int(arguments.get("limit"), 10))}
        if name == "get_recent_changes":
            return {"changes": await self.storage.recent_position_changes(limit_int(arguments.get("limit"), 10))}
        if name == "get_top_wallet_by_position_value":
            return {"top_wallet": await self.storage.largest_position_value_wallet()}
        if name == "get_latest_positions":
            wallet = arguments.get("wallet")
            snapshot = None
            if wallet:
                snapshot = await self.storage.latest_snapshot(wallet, self.settings.liquidation_alert_percent)
            else:
                snapshot = await self.storage.latest_any_snapshot(self.settings.liquidation_alert_percent)
            return {"snapshot": dump_snapshot(snapshot)}
        if name == "refresh_wallet_state":
            wallet = arguments["wallet"]
            result = await self.refresh_callback(wallet)
            return result
        raise ValueError(f"Unknown tool: {name}")


def limit_int(value: Any, default: int) -> int:
    try:
        return max(1, min(50, int(value)))
    except (TypeError, ValueError):
        return default


def dump_snapshot(snapshot: AccountSnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return snapshot.model_dump(mode="json")


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_latest_positions",
            "description": "Get the latest stored position snapshot. If wallet is omitted, use the latest snapshot across all wallets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet": {"type": "string", "description": "Optional 0x wallet address."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refresh_wallet_state",
            "description": "Fetch fresh Hyperliquid state for a wallet, save it, calculate alerts and position changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "wallet": {"type": "string", "description": "0x wallet address."},
                },
                "required": ["wallet"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_alerts",
            "description": "Get recent liquidation or risk alerts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_changes",
            "description": "Get recent position change events such as opened, closed, increased, reduced, or flipped.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_wallet_by_position_value",
            "description": "Find the wallet with the largest latest total position value among stored snapshots.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
