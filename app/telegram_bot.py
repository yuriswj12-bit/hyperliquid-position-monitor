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
            "Hyperdress.AI bot is online.\n"
            "Commands:\n"
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
            "Plain-text examples:\n"
            "recent alerts\n"
            "recent changes\n"
            "largest position value wallet\n"
            "positions 0x...",
        )

    async def status_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        configured = self.settings.watched_wallets
        database_wallets = await self.storage.list_watched_wallets()
        text = [
            "Hyperdress.AI status",
            f"Configured wallets: {len(configured)}",
            f"Database watchlist: {len(database_wallets)}",
            f"Refresh interval: {self.settings.monitor_interval_seconds}s",
            f"Liquidation alert: {self.settings.liquidation_alert_percent:g}%",
            f"Position change alert: {self.settings.position_change_alert_percent:g}%",
            f"Alert cooldown: {self.settings.alert_cooldown_seconds}s",
            f"AI analyst: {'enabled' if self.analyst and self.analyst.enabled else 'disabled'}",
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
            await self.reply(update, "No database watchlist wallets yet. Use /addwallet 0x... name")
            return

        lines = ["Watchlist"]
        for wallet in wallets[:30]:
            lines.append(f"- {format_wallet_label(wallet)}")
        await self.reply(update, "\n".join(lines))

    async def fills_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "Usage: /fills 0x... [limit]")
            return

        limit = parse_limit(context.args[1:], default=10, maximum=20)
        fills = await self.storage.recent_fills(context.args[0], limit)
        await self.reply(update, fills_report(context.args[0], fills, limit))

    async def refresh_fills_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "Usage: /refreshfills 0x...")
            return
        if not self.fills_callback:
            await self.reply(update, "Fills refresh is not available.")
            return

        try:
            result = await self.fills_callback(context.args[0])
        except Exception as error:
            await self.reply(update, f"Failed to refresh fills: {error}")
            return
        fills = await self.storage.recent_fills(context.args[0], 10)
        await self.reply(
            update,
            f"Fetched {result['fetched_count']} fills, saved {result['saved_count']} new fills.\n\n"
            f"{fills_report(context.args[0], fills, 10)}",
        )

    async def add_wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "Usage: /addwallet 0x... name")
            return

        user = context.args[0]
        name = " ".join(context.args[1:]).strip() or None
        wallet = await self.storage.upsert_watched_wallet(WatchedWalletRequest(user=user, name=name))
        await self.reply(update, f"Added to watchlist: {format_wallet_label(wallet)}")

    async def remove_wallet_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "Usage: /removewallet 0x...")
            return

        deleted = await self.storage.delete_watched_wallet(context.args[0])
        if deleted:
            await self.reply(update, f"Removed from watchlist: {short_wallet(context.args[0])}")
        else:
            await self.reply(update, "Wallet is not in the database watchlist.")

    async def refresh_wallets_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        wallets = await self.storage.active_wallet_addresses(self.settings.watched_wallets)
        if not wallets:
            await self.reply(update, "No wallets to refresh. Add one with /addwallet 0x... name")
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
        lines = [f"Refreshed {success_count}/{len(results)} wallets"]
        for result in results[:15]:
            if result["ok"]:
                lines.append(
                    f"- {short_wallet(result['user'])}: "
                    f"{result['positions']} positions, {result['changes']} changes, {result['alerts']} alerts"
                )
            else:
                lines.append(f"- {short_wallet(result['user'])}: failed - {result['error']}")
        await self.reply(update, "\n".join(lines))

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        wallet = context.args[0] if context.args else None
        if wallet:
            if not is_wallet(wallet):
                await self.reply(update, "Usage: /positions 0x...")
                return
            try:
                result = await self.refresh_callback(wallet)
                snapshot = AccountSnapshot.model_validate(result["snapshot"])
            except Exception as error:
                await self.reply(update, f"Failed to refresh positions: {error}")
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
                await self.reply(update, "No snapshot yet. Use /positions 0x... first or add a wallet to the watchlist.")
                return

        await self.reply(update, format_positions(snapshot))

    async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        limit = parse_limit(context.args, default=5, maximum=20)
        alerts = await self.storage.recent_alerts(limit)
        if not alerts:
            await self.reply(update, "No alerts recorded.")
            return

        lines = ["Recent alerts"]
        for alert in alerts:
            lines.append(f"- [{alert['severity']}] {alert['coin']} {short_wallet(alert['user'])}: {alert['message']}")
        await self.reply(update, "\n".join(lines))

    async def changes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        limit = parse_limit(context.args, default=5, maximum=20)
        changes = await self.storage.recent_position_changes(limit)
        if not changes:
            await self.reply(update, "No position changes recorded.")
            return

        lines = ["Recent position changes"]
        for change in changes:
            percent = change["change_percent"]
            pct = "" if percent is None else f" ({percent:.2f}%)"
            lines.append(
                f"- {change['coin']} {change['change_type']}{pct}: "
                f"{change['previous_size']:g} -> {change['current_size']:g}"
            )
        await self.reply(update, "\n".join(lines))

    async def top_command(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        top = await self.storage.largest_position_value_wallet()
        if not top:
            await self.reply(update, "No snapshots recorded yet. Use /positions 0x... first.")
            return

        await self.reply(
            update,
            "Largest latest position value\n"
            f"Wallet: {short_wallet(top['user'])}\n"
            f"Position value: ${top['total_position_value']:,.2f}\n"
            f"Account value: ${top['account_value']:,.2f}\n"
            f"Margin used: ${top['total_margin_used']:,.2f}\n"
            f"Unrealized PnL: ${top['unrealized_pnl']:,.2f}\n"
            f"Updated: {top['captured_at']}",
        )

    async def summary_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "Usage: /summary 0x... [hours]")
            return

        hours = parse_limit(context.args[1:], default=24, maximum=720)
        summary = await self.storage.wallet_summary(context.args[0], hours)
        await self.reply(update, format_wallet_summary(summary))

    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or not is_wallet(context.args[0]):
            await self.reply(update, "Usage: /report 0x... [hours]")
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

        if any(keyword in lowered for keyword in ["status", "state", "config", "monitor"]):
            await self.status_command(update, context)
            return

        if any(keyword in lowered for keyword in ["watchlist", "wallets", "address list", "monitor list"]):
            await self.wallets_command(update, context)
            return

        if "refresh" in lowered and any(keyword in lowered for keyword in ["wallet", "watchlist", "monitor"]):
            await self.refresh_wallets_command(update, context)
            return

        if any(keyword in lowered for keyword in ["top", "largest"]) and any(
            keyword in lowered for keyword in ["position", "address", "wallet"]
        ):
            await self.top_command(update, context)
            return

        if wallet or any(keyword in lowered for keyword in ["position", "positions"]):
            if wallet:
                context.args = [wallet]
            await self.positions_command(update, context)
            return

        if any(keyword in lowered for keyword in ["alert", "alerts", "risk", "liquidation"]):
            await self.alerts_command(update, context)
            return

        if any(keyword in lowered for keyword in ["change", "changes", "opened", "closed", "increased", "reduced"]):
            await self.changes_command(update, context)
            return

        await self.reply(
            update,
            "AI analyst is not available, so I used command mode.\n"
            "Try:\n"
            "- recent alerts\n"
            "- recent changes\n"
            "- positions 0x...\n"
            "- watchlist\n"
            "- status",
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
    latest = wallet.get("latest_snapshot_at") or "never"
    return f"{label}{tags}: {short_wallet(wallet['user'])} | snapshots {snapshot_count} | latest {latest}"


def parse_limit(args: list[str], default: int, maximum: int) -> int:
    if not args:
        return default
    try:
        return max(1, min(maximum, int(args[0])))
    except ValueError:
        return default


def format_positions(snapshot: AccountSnapshot) -> str:
    lines = [
        f"Positions for {short_wallet(snapshot.user)}",
        f"Account value: ${snapshot.account_value:,.2f}",
        f"Margin used: ${snapshot.total_margin_used:,.2f}",
        f"Unrealized PnL: ${snapshot.unrealized_pnl:,.2f}",
    ]

    if not snapshot.positions:
        lines.append("No open positions.")
        return "\n".join(lines)

    for position in snapshot.positions:
        distance = position.liquidation_distance_percent
        distance_text = "-" if distance is None else f"{distance:.2f}%"
        lines.append(
            f"- {position.coin} {position.side} size {position.size:g}, "
            f"value ${position.position_value:,.2f}, PnL ${position.unrealized_pnl:,.2f}, "
            f"liq distance {distance_text}"
        )
    return "\n".join(lines)


def format_wallet_summary(summary: dict) -> str:
    latest = summary.get("latest")
    deltas = summary.get("deltas")
    lines = [
        f"Wallet summary for {short_wallet(summary['user'])}",
        f"Window: {summary['hours']}h",
        f"Snapshots: {summary['snapshot_count']} in window, {summary['total_snapshot_count']} total",
        f"Enough trend data: {'yes' if summary['data_sufficient'] else 'no'}",
    ]
    if not latest:
        lines.append("No snapshots yet. Run /refreshwallets or /positions 0x... first.")
        return "\n".join(lines)

    lines.extend(
        [
            f"Latest: {latest['captured_at']}",
            f"Account value: ${latest['account_value']:,.2f}",
            f"Position value: ${latest['total_position_value']:,.2f}",
            f"Unrealized PnL: ${latest['unrealized_pnl']:,.2f}",
            f"Positions: {latest['position_count']}",
        ]
    )
    risk = summary.get("risk") or {}
    nearest = risk.get("nearest_liquidation_position")
    if nearest:
        lines.extend(
            [
                "Risk:",
                f"- Nearest liquidation: {nearest['coin']} {nearest['side']} {nearest['distance_percent']:.2f}%",
                f"- Position value: ${nearest['position_value']:,.2f}",
            ]
        )
    else:
        lines.append("Risk: no open position with liquidation distance.")
    lines.append(f"Recent changes: {summary.get('recent_change_count', 0)}")
    if deltas and summary["data_sufficient"]:
        lines.extend(
            [
                "Deltas:",
                f"- Account value: ${deltas['account_value']:,.2f}",
                f"- Position value: ${deltas['total_position_value']:,.2f}",
                f"- Margin used: ${deltas['total_margin_used']:,.2f}",
                f"- Unrealized PnL: ${deltas['unrealized_pnl']:,.2f}",
            ]
        )
    return "\n".join(lines)
