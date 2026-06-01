from datetime import datetime, timezone
import unittest

from app.models import AccountSnapshot, PositionRisk
from app.risk import liquidation_distance, position_changes, severity_for_distance


class RiskTests(unittest.TestCase):
    def test_liquidation_distance_for_short_position(self) -> None:
        distance = liquidation_distance(
            {
                "szi": "-2",
                "positionValue": "146000",
                "liquidationPx": "96696.97",
            }
        )

        self.assertIsNotNone(distance)
        self.assertEqual(round(distance or 0, 2), 32.46)

    def test_severity_for_distance_thresholds(self) -> None:
        self.assertEqual(severity_for_distance(None, 12), "info")
        self.assertEqual(severity_for_distance(8, 12), "critical")
        self.assertEqual(severity_for_distance(20, 12), "warning")
        self.assertEqual(severity_for_distance(30, 12), "normal")

    def test_position_changes_detects_opened_reduced_and_flipped(self) -> None:
        previous = snapshot(
            [
                position("BTC", 1.0, 73000),
                position("ETH", 2.0, 8000),
                position("SOL", 5.0, 1000),
            ]
        )
        current = snapshot(
            [
                position("BTC", -1.0, 73000),
                position("ETH", 1.0, 4000),
                position("HYPE", 10.0, 300),
            ]
        )

        changes = position_changes(previous, current, threshold_percent=25)
        by_coin = {change.coin: change.change_type for change in changes}

        self.assertEqual(by_coin["BTC"], "flipped")
        self.assertEqual(by_coin["ETH"], "reduced")
        self.assertEqual(by_coin["SOL"], "closed")
        self.assertEqual(by_coin["HYPE"], "opened")


def snapshot(positions: list[PositionRisk]) -> AccountSnapshot:
    return AccountSnapshot(
        user="0x0000000000000000000000000000000000000001",
        captured_at=datetime.now(timezone.utc),
        account_value=1000,
        total_position_value=sum(position.position_value for position in positions),
        total_margin_used=100,
        withdrawable=900,
        unrealized_pnl=0,
        raw={},
        positions=positions,
    )


def position(coin: str, size: float, value: float) -> PositionRisk:
    return PositionRisk(
        coin=coin,
        side="long" if size >= 0 else "short",
        size=size,
        entry_px=None,
        liquidation_px=None,
        position_value=value,
        unrealized_pnl=0,
        return_on_equity=0,
        liquidation_distance_percent=None,
        severity="normal",
    )


if __name__ == "__main__":
    unittest.main()
