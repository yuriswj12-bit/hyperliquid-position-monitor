from datetime import datetime, timezone
import unittest

from app.models import AccountSnapshot, PositionRisk
from app.telegram_bot import format_positions, format_wallet_summary


USER = "0x0ddf9bae2af4b874b96d287a5ad42eb47138a902"


class TelegramFormattingTests(unittest.TestCase):
    def test_format_positions_uses_chinese_labels(self) -> None:
        text = format_positions(
            AccountSnapshot(
                user=USER,
                captured_at=datetime.now(timezone.utc),
                account_value=1000,
                total_position_value=73000,
                total_margin_used=500,
                withdrawable=500,
                unrealized_pnl=-100,
                raw={},
                positions=[
                    PositionRisk(
                        coin="BTC",
                        side="short",
                        size=-1,
                        entry_px=73000,
                        liquidation_px=96696.97,
                        position_value=73000,
                        unrealized_pnl=-100,
                        return_on_equity=0,
                        liquidation_distance_percent=32.46,
                        severity="normal",
                    )
                ],
            )
        )

        self.assertIn("仓位：0x0ddf...a902", text)
        self.assertIn("空头", text)
        self.assertIn("强平距离 32.46%", text)
        self.assertNotIn("Positions for", text)

    def test_format_wallet_summary_uses_chinese_labels(self) -> None:
        text = format_wallet_summary(
            {
                "user": USER,
                "hours": 24,
                "snapshot_count": 2,
                "total_snapshot_count": 2,
                "data_sufficient": True,
                "latest": {
                    "captured_at": "2026-06-01T00:00:00+00:00",
                    "account_value": 1000,
                    "total_position_value": 73000,
                    "unrealized_pnl": -100,
                    "position_count": 1,
                },
                "risk": {"nearest_liquidation_position": None},
                "recent_change_count": 0,
                "deltas": {
                    "account_value": 10,
                    "total_position_value": 20,
                    "total_margin_used": 30,
                    "unrealized_pnl": -40,
                },
            }
        )

        self.assertIn("钱包摘要：0x0ddf...a902", text)
        self.assertIn("趋势数据：充足", text)
        self.assertIn("窗口变化", text)
        self.assertNotIn("Wallet summary", text)


if __name__ == "__main__":
    unittest.main()
