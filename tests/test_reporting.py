import unittest

from app.reporting import fills_report, grouped_fills, translate_direction


USER = "0x0ddf9bae2af4b874b96d287a5ad42eb47138a902"


class ReportingTests(unittest.TestCase):
    def test_grouped_fills_merges_same_second_coin_direction_and_price(self) -> None:
        groups = grouped_fills(
            [
                fill("2.12541", "12.412394", 1779947795151),
                fill("0.05995", "0.350108", 1779947795078),
                fill("1.0", "5.84", 1779947794000),
            ]
        )

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["count"], 2)
        self.assertEqual(round(groups[0]["size"], 6), 2.18536)
        self.assertEqual(round(groups[0]["fee"], 2), 12.76)

    def test_fills_report_is_compact_chinese_output(self) -> None:
        report = fills_report(
            USER,
            [
                fill("2.12541", "12.412394", 1779947795151),
                fill("0.05995", "0.350108", 1779947795078),
            ],
        )

        self.assertIn("最近成交", report)
        self.assertIn("0x0ddf...a902", report)
        self.assertIn("开仓做空", report)
        self.assertIn("数量 2.185360", report)
        self.assertIn("73,000.00", report)
        self.assertNotIn("Open Short", report)
        self.assertNotIn("fills", report)

    def test_translate_direction_known_values(self) -> None:
        self.assertEqual(translate_direction("Open Long"), "开仓做多")
        self.assertEqual(translate_direction("Open Short"), "开仓做空")
        self.assertEqual(translate_direction("Close Long"), "平多")
        self.assertEqual(translate_direction("Close Short"), "平空")


def fill(size: str, fee: str, timestamp: int) -> dict:
    return {
        "coin": "BTC",
        "dir": "Open Short",
        "px": "73000",
        "sz": size,
        "fee": fee,
        "closed_pnl": "0",
        "time": timestamp,
    }


if __name__ == "__main__":
    unittest.main()
