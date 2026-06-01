from collections.abc import Awaitable, Callable
import logging
from typing import Protocol

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import Settings
from app.models import AccountSnapshot, WatchedWalletRequest
from app.reporting import fills_report, wallet_report
from app.storage import Storage

RefreshCallback = Callable[[str], Awaitable[dict]]
FillsCallback = Callable[[str], Awaitable[dict]]
logger = logging.getLogger("hyperdress.telegram")


class Analyst(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def answer(self, user_text: str) -> str | None: ...


class TelegramCommandBot:
    def __init__(
        self,
        settings: Settings,
        storage: Storage,
        refresh_callback: RefreshCallback,
        fills_callback: FillsCallback | None = None,
        analyst: Analyst | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.refresh_callback = refresh_callback
        self.fills_callback = fills_callback
        self.analyst = analyst
        self.application: Application | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    async def start(self) -> None:
        if not self.enabled:
            return

        try:
            builder = ApplicationBuilder().token(self.settings.telegram_bot_token)
            if self.settings.telegram_proxy_url:
                builder = builder.proxy(self.settings.telegram_proxy_url).get_updates_proxy(self.settings.telegram_proxy_url)

            self.application = builder.build()
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("positions", self.positions_command))
            self.application.add_handler(CommandHandler("alerts", self.alerts_command))
            self.application.add_handler(CommandHandler("changes", self.changes_command))
            self.application.add_handler(CommandHandler("fills", self.fills_command))
            self.application.add_handler(CommandHandler("refreshfills", self.refresh_fills_command))
            self.application.add_handler(CommandHandler("top", self.top_command))
            self.application.add_handler(CommandHandler("summary", self.summary_command))
            self.application.add_handler(CommandHandler("report", self.report_command))
            self.application.add_handler(CommandHandler("wallets", self.wallets_command))
            self.application.add_handler(CommandHandler("addwallet", self.add_wallet_command))
            self.application.add_handler(CommandHandler("removewallet", self.remove_wallet_command))
            self.application.add_handler(CommandHandler("refreshwallets", self.refresh_wallets_command))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_message))

            await self.application.initialize()
            await self.application.start()
            if self.application.updater:
                await self.application.updater.start_polling()
            logger.info("telegram bot started")
        except Exception as error:
            self.application = None
            logger.exception("telegram bot start failed")

    async def stop(self) -> None:
        if not self.application:
            return

        if self.application.updater:
            await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        self.application = None
        logger.info("telegram bot stopped")

    async def start_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        await self.reply(
            update,
            "Hyperdress.AI 机器人已在线。\n"
            "可用命令：\n"
            "/status\n"
            "/positions <wallet>\n"
            "/alerts\n"
            "/changes\n"
            "/fills <wallet>\n"
            "/refreshfills <wallet>\n"
            "/top\n"
            "/summary <wallet> [hours]\n"
            "/report <wallet> [hours]\n"
            "/wallets\n"
            "/addwallet <wallet> <name>\n"
            "/removewallet <wallet>\n"
            "/refreshwallets\n\n"
            "自然语言示例：\n"
            "最近告警\n"
            "最近仓位变化\n"
            "仓位价值最大的地址\n"
            "查看 0x... 的仓位",
        )

    async def status_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        configured = self.settings.watched_wallets
        database_wallets = await self.storage.list_watched_wallets()
        text = [
            "Hyperdress.AI 状态",
            f"配置文件钱包数：{len(configured)}",
            f"数据库监控列表：{len(database_wallets)}",
            f"刷新间隔：{self.settings.monitor_interval_seconds}s",
            f"强平距离告警阈值：{self.settings.liquidation_alert_percent:g}%",
            f"仓位变化告警阈值：{self.settings.position_change_alert_percent:g}%",
            f"告警冷却：{self.settings.alert_cooldown_seconds}s",
            f"AI 分析：{'已启用' if self.analyst and self.analyst.enabled else '未启用'}",
        ]
        if database_wallets:
            text.append("")
            text.extend(format_wallet_label(wallet) for wallet in database_wallets[:10])
        elif configured:
            text.append("")
            text.extend(short_wallet(wallet) for wallet in configured[:10])
        await self.reply(update, "\n".join(text))

    async def wallets_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        wallets = await self.storage.list_watched_wallets()
        if not wallets:
            await self.reply(update, "数据库监控列表为空。使用 /addwallet 0x... 名称 添加。")
            return

        lines = ["监控列表"]
        for wallet in wallets[:30]:
            lines.append(f"- {format_wallet_label(wallet)}")
        await self.reply(update, "\n".join(lines))

    async def fills_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "用法：/fills 0x... [数量]")
            return

        limit = parse_limit(context.args[1:], default=10, maximum=20)
        fills = await self.storage.recent_fills(context.args[0], limit)
        await self.reply(update, fills_report(context.args[0], fills, limit))

    async def refresh_fills_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "用法：/refreshfills 0x...")
            return
        if not self.fills_callback:
            await self.reply(update, "成交刷新功能暂不可用。")
            return

        try:
            result = await self.fills_callback(context.args[0])
        except Exception as error:
            await self.reply(update, f"刷新成交失败：{error}")
            return
        fills = await self.storage.recent_fills(context.args[0], 10)
        await self.reply(
            update,
            f"已拉取 {result['fetched_count']} 条成交，新增保存 {result['saved_count']} 条。\n\n"
            f"{fills_report(context.args[0], fills, 10)}",
        )

    async def add_wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "用法：/addwallet 0x... 名称")
            return

        user = context.args[0]
        name = " ".join(context.args[1:]).strip() or None
        wallet = await self.storage.upsert_watched_wallet(WatchedWalletRequest(user=user, name=name))
        await self.reply(update, f"已加入监控列表：{format_wallet_label(wallet)}")

    async def remove_wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "用法：/removewallet 0x...")
            return

        deleted = await self.storage.delete_watched_wallet(context.args[0])
        if deleted:
            await self.reply(update, f"已移出监控列表：{short_wallet(context.args[0])}")
        else:
            await self.reply(update, "该钱包不在数据库监控列表中。")

    async def refresh_wallets_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        wallets = await self.storage.active_wallet_addresses(self.settings.watched_wallets)
        if not wallets:
            await self.reply(update, "暂无可刷新的钱包。使用 /addwallet 0x... 名称 添加。")
            return

        results = []
        for wallet in wallets:
            try:
                result = await self.refresh_callback(wallet)
                results.append(
                    {
                        "user": wallet,
                        "ok": True,
                        "positions": len(result["snapshot"].get("positions", [])),
                        "changes": len(result["changes"]),
                        "alerts": len(result["alerts"]),
                    }
                )
            except Exception as error:
                results.append({"user": wallet, "ok": False, "error": str(error)})

        success_count = sum(1 for result in results if result["ok"])
        lines = [f"已刷新 {success_count}/{len(results)} 个钱包"]
        for result in results[:15]:
            if result["ok"]:
                lines.append(
                    f"- {short_wallet(result['user'])}: "
                    f"{result['positions']} 个仓位，{result['changes']} 个变化，{result['alerts']} 个告警"
                )
            else:
                lines.append(f"- {short_wallet(result['user'])}: 失败 - {result['error']}")
        await self.reply(update, "\n".join(lines))

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        wallet = context.args[0] if context.args else None
        if wallet:
            if not is_wallet(wallet):
                await self.reply(update, "用法：/positions 0x...")
                return
            try:
                result = await self.refresh_callback(wallet)
                snapshot = AccountSnapshot.model_validate(result["snapshot"])
            except Exception as error:
                await self.reply(update, f"刷新仓位失败：{error}")
                return
        else:
            database_wallets = await self.storage.list_watched_wallets()
            wallet = (
                database_wallets[0]["user"]
                if database_wallets
                else self.settings.watched_wallets[0]
                if self.settings.watched_wallets
                else None
            )
            snapshot = (
                await self.storage.latest_snapshot(wallet, self.settings.liquidation_alert_percent)
                if wallet
                else await self.storage.latest_any_snapshot(self.settings.liquidation_alert_percent)
            )
            if snapshot is None:
                await self.reply(update, "暂无快照。请先使用 /positions 0x...，或把钱包加入监控列表。")
                return

        await self.reply(update, format_positions(snapshot))

    async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        limit = parse_limit(context.args, default=5, maximum=20)
        alerts = await self.storage.recent_alerts(limit)
        if not alerts:
            await self.reply(update, "暂无告警记录。")
            return

        lines = ["最近告警"]
        for alert in alerts:
            lines.append(
                f"- [{translate_severity(alert['severity'])}] {alert['coin']} "
                f"{short_wallet(alert['user'])}: {alert['message']}"
            )
        await self.reply(update, "\n".join(lines))

    async def changes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        limit = parse_limit(context.args, default=5, maximum=20)
        changes = await self.storage.recent_position_changes(limit)
        if not changes:
            await self.reply(update, "暂无仓位变化记录。")
            return

        lines = ["最近仓位变化"]
        for change in changes:
            percent = change["change_percent"]
            pct = "" if percent is None else f" ({percent:.2f}%)"
            lines.append(
                f"- {change['coin']} {translate_change_type(change['change_type'])}{pct}: "
                f"{change['previous_size']:g} -> {change['current_size']:g}"
            )
        await self.reply(update, "\n".join(lines))

    async def top_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        top = await self.storage.largest_position_value_wallet()
        if not top:
            await self.reply(update, "暂无快照记录。请先使用 /positions 0x...。")
            return

        await self.reply(
            update,
            "当前仓位价值最大的地址\n"
            f"钱包：{short_wallet(top['user'])}\n"
            f"仓位价值：${top['total_position_value']:,.2f}\n"
            f"账户价值：${top['account_value']:,.2f}\n"
            f"保证金使用：${top['total_margin_used']:,.2f}\n"
            f"未实现盈亏：${top['unrealized_pnl']:,.2f}\n"
            f"更新时间：{top['captured_at']}",
        )

    async def summary_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "用法：/summary 0x... [小时]")
            return

        hours = parse_limit(context.args[1:], default=24, maximum=720)
        summary = await self.storage.wallet_summary(context.args[0], hours)
        await self.reply(update, format_wallet_summary(summary))

    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "用法：/report 0x... [小时]")
            return

        hours = parse_limit(context.args[1:], default=24, maximum=720)
        summary = await self.storage.wallet_summary(context.args[0], hours)
        await self.reply(update, wallet_report(summary))

    async def text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text.strip() if update.message and update.message.text else ""
        if not text:
            return

        if self.analyst and self.analyst.enabled:
            try:
                answer = await self.analyst.answer(text)
                if answer:
                    await self.reply(update, answer)
                    return
            except Exception as error:
                logger.exception("ai analyst failed")

        await self.keyword_fallback(update, context, text)

    async def keyword_fallback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        lowered = text.lower()
        wallet = first_wallet(text)

        if any(keyword in lowered for keyword in ["status", "state", "config", "monitor", "状态", "配置", "监控"]):
            await self.status_command(update, context)
            return

        if any(keyword in lowered for keyword in ["watchlist", "wallets", "address list", "monitor list", "钱包", "地址列表", "监控列表"]):
            await self.wallets_command(update, context)
            return

        if ("refresh" in lowered or "刷新" in lowered) and any(
            keyword in lowered for keyword in ["wallet", "watchlist", "monitor", "钱包", "监控", "列表"]
        ):
            await self.refresh_wallets_command(update, context)
            return

        if any(keyword in lowered for keyword in ["top", "largest", "最大", "最高"]) and any(
            keyword in lowered for keyword in ["position", "address", "wallet", "仓位", "地址", "钱包"]
        ):
            await self.top_command(update, context)
            return

        if wallet or any(keyword in lowered for keyword in ["position", "positions", "仓位", "持仓"]):
            if wallet:
                context.args = [wallet]
            await self.positions_command(update, context)
            return

        if any(keyword in lowered for keyword in ["alert", "alerts", "risk", "liquidation", "告警", "风险", "强平"]):
            await self.alerts_command(update, context)
            return

        if any(keyword in lowered for keyword in ["change", "changes", "opened", "closed", "increased", "reduced", "变化", "开仓", "平仓", "加仓", "减仓"]):
            await self.changes_command(update, context)
            return

        await self.reply(
            update,
            "AI 分析暂不可用，已切换到命令模式。\n"
            "可尝试：\n"
            "- 最近告警\n"
            "- 最近仓位变化\n"
            "- 查看 0x... 的仓位\n"
            "- 监控列表\n"
            "- 状态",
        )

    async def reply(self, update: Update, text: str) -> None:
        if update.effective_chat is None:
            return
        allowed_chat = str(self.settings.telegram_chat_id)
        if str(update.effective_chat.id) != allowed_chat:
            return
        if update.message:
            await update.message.reply_text(text[:3900], disable_web_page_preview=True)


def is_wallet(value: str) -> bool:
    return value.startswith("0x") and len(value) == 42 and all(char in "0123456789abcdefABCDEF" for char in value[2:])


def first_wallet(text: str) -> str | None:
    for raw in text.replace(",", " ").replace("\n", " ").split():
        candidate = raw.strip()
        if is_wallet(candidate):
            return candidate
    return None


def short_wallet(wallet: str) -> str:
    return f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 12 else wallet


def format_wallet_label(wallet: dict) -> str:
    label = wallet.get("name") or short_wallet(wallet["user"])
    tags = f" [{wallet['tags']}]" if wallet.get("tags") else ""
    snapshot_count = wallet.get("snapshot_count") or 0
    latest = wallet.get("latest_snapshot_at") or "暂无"
    return f"{label}{tags}: {short_wallet(wallet['user'])} | 快照 {snapshot_count} | 最新 {latest}"


def parse_limit(args: list[str], default: int, maximum: int) -> int:
    if not args:
        return default
    try:
        return max(1, min(maximum, int(args[0])))
    except ValueError:
        return default


def format_positions(snapshot: AccountSnapshot) -> str:
    lines = [
        f"仓位：{short_wallet(snapshot.user)}",
        f"账户价值：${snapshot.account_value:,.2f}",
        f"保证金使用：${snapshot.total_margin_used:,.2f}",
        f"未实现盈亏：${snapshot.unrealized_pnl:,.2f}",
    ]

    if not snapshot.positions:
        lines.append("当前没有开放仓位。")
        return "\n".join(lines)

    for position in snapshot.positions:
        distance = position.liquidation_distance_percent
        distance_text = "-" if distance is None else f"{distance:.2f}%"
        lines.append(
            f"- {position.coin} {translate_side(position.side)} 数量 {position.size:g}，"
            f"价值 ${position.position_value:,.2f}，盈亏 ${position.unrealized_pnl:,.2f}，"
            f"强平距离 {distance_text}"
        )
    return "\n".join(lines)


def format_wallet_summary(summary: dict) -> str:
    latest = summary.get("latest")
    deltas = summary.get("deltas")
    lines = [
        f"钱包摘要：{short_wallet(summary['user'])}",
        f"窗口：{summary['hours']} 小时",
        f"快照：窗口内 {summary['snapshot_count']} 条，总计 {summary['total_snapshot_count']} 条",
        f"趋势数据：{'充足' if summary['data_sufficient'] else '不足'}",
    ]
    if not latest:
        lines.append("暂无快照。请先执行 /refreshwallets 或 /positions 0x...。")
        return "\n".join(lines)

    lines.extend(
        [
            f"最新时间：{latest['captured_at']}",
            f"账户价值：${latest['account_value']:,.2f}",
            f"仓位价值：${latest['total_position_value']:,.2f}",
            f"未实现盈亏：${latest['unrealized_pnl']:,.2f}",
            f"持仓数量：{latest['position_count']}",
        ]
    )
    risk = summary.get("risk") or {}
    nearest = risk.get("nearest_liquidation_position")
    if nearest:
        lines.extend(
            [
                "风险：",
                f"- 最近强平距离：{nearest['coin']} {translate_side(nearest['side'])} {nearest['distance_percent']:.2f}%",
                f"- 仓位价值：${nearest['position_value']:,.2f}",
            ]
        )
    else:
        lines.append("风险：当前没有可计算强平距离的开放仓位。")
    lines.append(f"最近仓位变化：{summary.get('recent_change_count', 0)}")
    if deltas and summary["data_sufficient"]:
        lines.extend(
            [
                "窗口变化：",
                f"- 账户价值：${deltas['account_value']:,.2f}",
                f"- 仓位价值：${deltas['total_position_value']:,.2f}",
                f"- 保证金使用：${deltas['total_margin_used']:,.2f}",
                f"- 未实现盈亏：${deltas['unrealized_pnl']:,.2f}",
            ]
        )
    return "\n".join(lines)


def translate_side(value: object) -> str:
    side = str(value or "").lower()
    if side == "long":
        return "多头"
    if side == "short":
        return "空头"
    return str(value or "-")


def translate_severity(value: object) -> str:
    severity = str(value or "").lower()
    return {
        "critical": "严重",
        "warning": "警告",
        "normal": "正常",
        "info": "信息",
    }.get(severity, str(value or "-"))


def translate_change_type(value: object) -> str:
    change_type = str(value or "").lower()
    return {
        "opened": "开仓",
        "closed": "平仓",
        "increased": "加仓",
        "reduced": "减仓",
        "flipped": "反手",
    }.get(change_type, str(value or "-"))
