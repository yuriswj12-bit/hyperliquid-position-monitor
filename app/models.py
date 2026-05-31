from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WalletRequest(BaseModel):
    user: str = Field(pattern=r"^0x[a-fA-F0-9]{40}$")


class HyperliquidStateRequest(WalletRequest):
    endpoint: str | None = None
    dex: str | None = None


class PositionRisk(BaseModel):
    coin: str
    side: str
    size: float
    entry_px: float | None
    liquidation_px: float | None
    position_value: float
    unrealized_pnl: float
    return_on_equity: float
    liquidation_distance_percent: float | None
    severity: str


class AccountSnapshot(BaseModel):
    user: str
    captured_at: datetime
    account_value: float
    total_position_value: float
    total_margin_used: float
    withdrawable: float
    unrealized_pnl: float
    raw: dict[str, Any]
    positions: list[PositionRisk]


class AlertEvent(BaseModel):
    user: str
    coin: str
    severity: str
    message: str
    created_at: datetime
