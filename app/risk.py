from datetime import datetime, timezone
from typing import Any

from app.models import AccountSnapshot, AlertEvent, PositionChange, PositionRisk


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
                fingerprint=f"liquidation:{snapshot.user}:{position.coin}:{position.severity}",
            )
        )
    return events


def _position_index(snapshot: AccountSnapshot) -> dict[str, PositionRisk]:
    return {position.coin: position for position in snapshot.positions if abs(position.size) > 0}


def _change_percent(previous: float, current: float) -> float | None:
    previous_abs = abs(previous)
    if previous_abs == 0:
        return None
    return ((abs(current) - previous_abs) / previous_abs) * 100


def position_changes(
    previous: AccountSnapshot | None,
    current: AccountSnapshot,
    threshold_percent: float,
) -> list[PositionChange]:
    if previous is None:
        return []

    changes: list[PositionChange] = []
    previous_positions = _position_index(previous)
    current_positions = _position_index(current)
    coins = sorted(set(previous_positions) | set(current_positions))

    for coin in coins:
        old = previous_positions.get(coin)
        new = current_positions.get(coin)
        old_size = old.size if old else 0.0
        new_size = new.size if new else 0.0
        old_value = old.position_value if old else 0.0
        new_value = new.position_value if new else 0.0
        change_percent = _change_percent(old_size, new_size)
        change_type: str | None = None

        if old is None and new is not None:
            change_type = "opened"
        elif old is not None and new is None:
            change_type = "closed"
        elif old is not None and new is not None and old_size * new_size < 0:
            change_type = "flipped"
        elif change_percent is not None and change_percent >= threshold_percent:
            change_type = "increased"
        elif change_percent is not None and change_percent <= -threshold_percent:
            change_type = "reduced"

        if not change_type:
            continue

        changes.append(
            PositionChange(
                user=current.user,
                coin=coin,
                change_type=change_type,
                previous_size=old_size,
                current_size=new_size,
                previous_value=old_value,
                current_value=new_value,
                change_percent=change_percent,
                message=f"{coin} position {change_type}: {old_size:g} -> {new_size:g}.",
                created_at=current.captured_at,
            )
        )

    return changes
