from datetime import datetime, timezone


def wallet_report(summary: dict) -> str:
    latest = summary.get("latest")
    if not latest:
        return (
            f"钱包 {short_wallet(summary['user'])} 暂无快照。\n"
            "请先执行 /refreshwallets 或 /positions 0x... 采集数据。"
        )

    risk = summary.get("risk") or {}
    nearest = risk.get("nearest_liquidation_position")
    deltas = summary.get("deltas") or {}

    lines = [
        f"钱包风险报告：{short_wallet(summary['user'])}",
        f"数据：近 {summary['hours']} 小时 {summary['snapshot_count']} 条快照，总计 {summary['total_snapshot_count']} 条；趋势数据{'充足' if summary['data_sufficient'] else '不足'}。",
        "",
        "当前状态",
        f"- 账户价值：{money(latest['account_value'])}",
        f"- 仓位价值：{money(latest['total_position_value'])}",
        f"- 未实现盈亏：{money(latest['unrealized_pnl'])}",
        f"- 持仓数量：{latest['position_count']}",
    ]

    if nearest:
        lines.extend(
            [
                "",
                "主要风险",
                f"- 最近强平距离：{percent(nearest['distance_percent'])}",
                f"- 仓位：{nearest['coin']} {translate_side(nearest['side'])}",
                f"- 强平价：{number(nearest['liquidation_px'], 2)}",
                f"- 仓位价值：{money(nearest['position_value'])}",
                f"- 未实现盈亏：{money(nearest['unrealized_pnl'])}",
            ]
        )
    else:
        lines.extend(["", "主要风险", "- 当前没有可计算强平距离的开放仓位。"])

    lines.extend(
        [
            "",
            "窗口变化",
            f"- 账户价值：{signed_money(deltas.get('account_value'))}",
            f"- 仓位价值：{signed_money(deltas.get('total_position_value'))}",
            f"- 保证金使用：{signed_money(deltas.get('total_margin_used'))}",
            f"- 未实现盈亏：{signed_money(deltas.get('unrealized_pnl'))}",
            f"- 最近仓位变化事件：{summary.get('recent_change_count', 0)}",
        ]
    )

    return "\n".join(lines)


def fills_report(user: str, fills: list[dict], limit: int = 10) -> str:
    visible = fills[: max(1, min(limit, 20))]
    if not visible:
        return f"钱包 {short_wallet(user)} 暂无成交记录。请先执行 /refreshfills {user}。"

    total_size = sum(float_or_zero(fill.get("sz")) for fill in visible)
    total_fee = sum(float_or_zero(fill.get("fee")) for fill in visible)
    total_closed_pnl = sum(float_or_zero(fill.get("closed_pnl")) for fill in visible)
    coins = ", ".join(sorted({str(fill.get("coin")) for fill in visible if fill.get("coin")}))
    groups = grouped_fills(visible)

    lines = [
        f"最近成交：{short_wallet(user)}",
        f"显示 {len(visible)} 笔成交，合并为 {len(groups)} 组。币种：{coins or '-'}",
        f"总数量：{number(total_size, 6)} | 总手续费：{money(total_fee)} | 已实现盈亏：{money(total_closed_pnl)}",
        "",
    ]

    for group in groups:
        lines.append(
            f"- 时间：{group['time']} | {group['coin']} {translate_direction(group['direction'])} | "
            f"{group['count']} 笔 | 数量 {number(group['size'], 6)} | 价格 {number(group['price'], 2)} | "
            f"手续费 {money(group['fee'])} | 盈亏 {money(group['closed_pnl'])}"
        )
    return "\n".join(lines)


def grouped_fills(fills: list[dict]) -> list[dict]:
    groups: dict[tuple, dict] = {}
    order: list[tuple] = []
    for fill in fills:
        timestamp = second_timestamp(fill.get("time"))
        key = (
            timestamp,
            fill.get("coin") or "-",
            fill.get("dir") or fill.get("side") or "-",
            round(float_or_zero(fill.get("px")), 8),
        )
        if key not in groups:
            groups[key] = {
                "time": format_time(timestamp),
                "coin": key[1],
                "direction": key[2],
                "price": key[3],
                "count": 0,
                "size": 0.0,
                "fee": 0.0,
                "closed_pnl": 0.0,
            }
            order.append(key)
        groups[key]["count"] += 1
        groups[key]["size"] += float_or_zero(fill.get("sz"))
        groups[key]["fee"] += float_or_zero(fill.get("fee"))
        groups[key]["closed_pnl"] += float_or_zero(fill.get("closed_pnl"))
    return [groups[key] for key in order]


def short_wallet(wallet: str) -> str:
    return f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 12 else wallet


def translate_side(value: object) -> str:
    side = str(value or "").lower()
    if side == "long":
        return "多头"
    if side == "short":
        return "空头"
    return str(value or "-")


def translate_direction(value: object) -> str:
    direction = str(value or "-")
    normalized = direction.lower()
    mapping = {
        "open long": "开仓做多",
        "open short": "开仓做空",
        "close long": "平多",
        "close short": "平空",
        "buy": "买入",
        "sell": "卖出",
        "b": "买入",
        "a": "卖出",
    }
    return mapping.get(normalized, direction)


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


def second_timestamp(value: object) -> int:
    timestamp = float_or_zero(value)
    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000
    return int(timestamp)


def float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
