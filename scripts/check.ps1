$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  throw ".venv not found. Run .\scripts\dev.ps1 once to create the environment."
}

Write-Host "Checking Python syntax..."
.\.venv\Scripts\python.exe -m compileall app

Write-Host "Checking application import..."
.\.venv\Scripts\python.exe -c "from app.main import app; print('import ok')"

Write-Host "Running unit tests..."
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
if ($LASTEXITCODE -ne 0) {
  throw "unit tests failed"
}

Write-Host "Running storage/reporting checks..."
@'
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from app.models import AccountSnapshot, WatchedWalletRequest
from app.reporting import fills_report, wallet_report
from app.storage import Storage

USER = "0x0000000000000000000000000000000000000001"

async def main():
    with TemporaryDirectory() as tmp:
        storage = Storage(Path(tmp) / "check.db")
        await storage.init()
        await storage.upsert_watched_wallet(WatchedWalletRequest(user=USER, name="Check Wallet", tags="test"))

        raw = {
            "assetPositions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "-1",
                        "positionValue": "73000",
                        "liquidationPx": "96696.97",
                        "unrealizedPnl": "-100",
                    }
                }
            ],
            "marginSummary": {},
        }
        for value in [1000, 1100]:
            await storage.save_snapshot(
                AccountSnapshot(
                    user=USER,
                    captured_at="2026-06-01T00:00:00+00:00",
                    account_value=value,
                    total_position_value=73000,
                    total_margin_used=1000,
                    withdrawable=100,
                    unrealized_pnl=-100,
                    raw=raw,
                    positions=[],
                )
            )

        summary = await storage.wallet_summary(USER, 24)
        assert summary["data_sufficient"] is True
        assert summary["risk"]["position_count"] == 1
        assert "0x0000...0001" in wallet_report(summary)

        fills = [
            {
                "coin": "BTC",
                "dir": "Open Short",
                "px": "73000",
                "sz": "1.5",
                "fee": "8.76",
                "closedPnl": "0",
                "time": 1779947795151,
                "hash": "0xabc",
                "oid": 1,
            },
            {
                "coin": "BTC",
                "dir": "Open Short",
                "px": "73000",
                "sz": "0.5",
                "fee": "2.92",
                "closedPnl": "0",
                "time": 1779947795078,
                "hash": "0xdef",
                "oid": 2,
            },
        ]
        saved = await storage.save_fills(USER, fills)
        assert saved == 2
        stored = await storage.recent_fills(USER, 10)
        report = fills_report(USER, stored, 10)
        assert "BTC" in report
        assert "73,000.00" in report

asyncio.run(main())
print("storage/reporting ok")
'@ | .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) {
  throw "storage/reporting checks failed"
}

Write-Host "All checks passed."
