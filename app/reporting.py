from datetime import datetime, timezone


def wallet_report(summary: dict) -> str:
    latest = summary.get("latest")
    if not latest:
        return (
            f"Wallet {short_wallet(summary['user'])} has no snapshots.\n"
            "Run /refreshwallets or /positions 0x... first."
        )

    risk = summary.get("risk") or {}
    nearest = risk.get("nearest_liquidation_position")
    deltas = summary.get("deltas") or {}

    lines = [
        f"Wallet risk report: {short_wallet(summary['user'])}",
        f"Data: {summary['snapshot_count']} snapshots/{summary['hours']}h, {summary['total_snapshot_count']} total; trend data {'enough' if summary['data_sufficient'] else 'not enough'}.",
        "",
        "Current",
        f"- Account value: {money(latest['account_value'])}",
        f"- Position value: {money(latest['total_position_value'])}",
        f"- Unrealized PnL: {money(latest['unrealized_pnl'])}",
        f"- Open positions: {latest['position_count']}",
    ]

    if nearest:
        lines.extend(
            [
                "",
                "Risk",
                f"- Nearest liquidation distance: {percent(nearest['distance_percent'])}",
                f"- Position: {nearest['coin']} {nearest['side']}",
                f"- Liquidation price: {number(nearest['liquidation_px'], 2)}",
                f"- Position value: {money(nearest['position_value'])}",
                f"- Unrealized PnL: {money(nearest['unrealized_pnl'])}",
            ]
        )
    else:
        lines.extend(["", "Risk", "- No open position with liquidation distance."])

    lines.extend(
        [
            "",
            "Window change",
            f"- Account value: {signed_money(deltas.get('account_value'))}",
            f"- Position value: {signed_money(deltas.get('total_position_value'))}",
            f"- Margin used: {signed_money(deltas.get('total_margin_used'))}",
            f"- Unrealized PnL: {signed_money(deltas.get('unrealized_pnl'))}",
            f"- Recent position-change events: {summary.get('recent_change_count', 0)}",
        ]
    )

    return "\n".join(lines)


def fills_report(user: str, fills: list[dict], limit: int = 10) -> str:
    visible = fills[: max(1, min(limit, 20))]
    if not visible:
        return f"No fills stored for {short_wallet(user)}. Run /refreshfills {user} first."

    total_size = sum(float_or_zero(fill.get("sz")) for fill in visible)
    total_fee = sum(float_or_zero(fill.get("fee")) for fill in visible)
    total_closed_pnl = sum(float_or_zero(fill.get("closed_pnl")) for fill in visible)
    coins = ", ".join(sorted({str(fill.get("coin")) for fill in visible if fill.get("coin")}))

    lines = [
        f"Recent fills: {short_wallet(user)}",
        f"Showing {len(visible)} fills. Coins: {coins or '-'}",
        f"Total size: {number(total_size, 6)} | Fees: {money(total_fee)} | Closed PnL: {money(total_closed_pnl)}",
        "",
    ]

    for fill in visible:
        direction = fill.get("dir") or fill.get("side") or "-"
        lines.append(
            f"- {format_time(fill.get('time'))} | {fill.get('coin') or '-'} {direction} | "
            f"sz {number(fill.get('sz'), 6)} @ {number(fill.get('px'), 2)} | "
            f"fee {money(fill.get('fee'))} | pnl {money(fill.get('closed_pnl'))}"
        )
    return "\n".join(lines)


def short_wallet(wallet: str) -> str:
    return f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 12 else wallet


def money(value: object) -> str:
    return f"${float_or_zero(value):,.2f}"


def signed_money(value: object) -> str:
    number_value = float_or_zero(value)
    sign = "+" if number_value > 0 else ""
    return f"{sign}${number_value:,.2f}"


def percent(value: object) -> str:
    return f"{float_or_zero(value):.2f}%"


def number(value: object, digits: int = 2) -> str:
    return f"{float_or_zero(value):,.{digits}f}"


def format_time(value: object) -> str:
    timestamp = float_or_zero(value)
    if timestamp <= 0:
        return "-"
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
