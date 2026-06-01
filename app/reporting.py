def wallet_report(summary: dict) -> str:
    latest = summary.get("latest")
    if not latest:
        return (
            f"钱包 {short_wallet(summary['user'])} 暂无快照。\n"
            "先执行 /refreshwallets 或 /positions 0x... 采集数据。"
        )

    risk = summary.get("risk") or {}
    nearest = risk.get("nearest_liquidation_position")
    deltas = summary.get("deltas") or {}

    lines = [
        f"钱包 {short_wallet(summary['user'])} 风险报告",
        f"数据：{summary['snapshot_count']} 条/{summary['hours']}h，总计 {summary['total_snapshot_count']} 条；趋势数据{'足够' if summary['data_sufficient'] else '不足'}。",
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
                f"- 仓位：{nearest['coin']} {nearest['side']}",
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


def float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
