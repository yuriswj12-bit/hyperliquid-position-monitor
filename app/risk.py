from datetime import datetime, timezone
from typing import Any

from app.models import AccountSnapshot, AlertEvent, PositionRisk


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def liquidation_distance(position: dict[str, Any]) -> float | None:
    liquidation_px = _number(position.get("liquidationPx"))
    position_value = _number(position.get("positionValue"))
    size = abs(_number(position.get("szi")))

    if not liquidation_px or not position_value or not size:
        return None

    mark_px = position_value / size
    if not mark_px:
        return None

    is_long = _number(position.get("szi")) > 0
    distance = ((mark_px - liquidation_px) / mark_px) * 100 if is_long else ((liquidation_px - mark_px) / mark_px) * 100
    return distance if distance >= 0 else 0.0


def severity_for_distance(distance: float | None, threshold: float) -> str:
    if distance is None:
        return "info"
    if distance <= threshold:
        return "critical"
    if distance <= threshold * 2:
        return "warning"
    return "normal"


def normalize_snapshot(user: str, raw: dict[str, Any], liquidation_threshold: float) -> AccountSnapshot:
    margin = raw.get("marginSummary") or {}
    positions: list[PositionRisk] = []
    total_pnl = 0.0

    for item in raw.get("assetPositions") or []:
        position = item.get("position") or {}
        size = _number(position.get("szi"))
        pnl = _number(position.get("unrealizedPnl"))
        total_pnl += pnl
        distance = liquidation_distance(position)
        positions.append(
            PositionRisk(
                coin=position.get("coin") or "-",
                side="long" if size >= 0 else "short",
                size=size,
                entry_px=_number(position.get("entryPx")) or None,
                liquidation_px=_number(position.get("liquidationPx")) or None,
                position_value=_number(position.get("positionValue")),
                unrealized_pnl=pnl,
                return_on_equity=_number(position.get("returnOnEquity")),
                liquidation_distance_percent=distance,
                severity=severity_for_distance(distance, liquidation_threshold),
            )
        )

    return AccountSnapshot(
        user=user,
        captured_at=datetime.now(timezone.utc),
        account_value=_number(margin.get("accountValue")),
        total_position_value=_number(margin.get("totalNtlPos")),
        total_margin_used=_number(margin.get("totalMarginUsed")),
        withdrawable=_number(raw.get("withdrawable")),
        unrealized_pnl=total_pnl,
        raw=raw,
        positions=positions,
    )


def liquidation_alerts(snapshot: AccountSnapshot) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    for position in snapshot.positions:
        if position.severity not in {"critical", "warning"}:
            continue
        distance = position.liquidation_distance_percent
        distance_text = "unknown" if distance is None else f"{distance:.2f}%"
        events.append(
            AlertEvent(
                user=snapshot.user,
                coin=position.coin,
                severity=position.severity,
                message=f"{position.coin} {position.side} is {distance_text} from liquidation.",
                created_at=snapshot.captured_at,
            )
        )
    return events
