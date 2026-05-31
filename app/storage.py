import json
from pathlib import Path

import aiosqlite

from app.models import AccountSnapshot, AlertEvent


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def init(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                create table if not exists snapshots (
                    id integer primary key autoincrement,
                    user text not null,
                    captured_at text not null,
                    account_value real not null,
                    total_position_value real not null,
                    total_margin_used real not null,
                    withdrawable real not null,
                    unrealized_pnl real not null,
                    raw_json text not null
                )
                """
            )
            await db.execute(
                """
                create table if not exists alerts (
                    id integer primary key autoincrement,
                    user text not null,
                    coin text not null,
                    severity text not null,
                    message text not null,
                    created_at text not null
                )
                """
            )
            await db.commit()

    async def save_snapshot(self, snapshot: AccountSnapshot) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                insert into snapshots (
                    user, captured_at, account_value, total_position_value,
                    total_margin_used, withdrawable, unrealized_pnl, raw_json
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.user,
                    snapshot.captured_at.isoformat(),
                    snapshot.account_value,
                    snapshot.total_position_value,
                    snapshot.total_margin_used,
                    snapshot.withdrawable,
                    snapshot.unrealized_pnl,
                    json.dumps(snapshot.raw),
                ),
            )
            await db.commit()

    async def save_alerts(self, events: list[AlertEvent]) -> None:
        if not events:
            return
        async with aiosqlite.connect(self.database_path) as db:
            await db.executemany(
                """
                insert into alerts (user, coin, severity, message, created_at)
                values (?, ?, ?, ?, ?)
                """,
                [(event.user, event.coin, event.severity, event.message, event.created_at.isoformat()) for event in events],
            )
            await db.commit()

    async def recent_alerts(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                select user, coin, severity, message, created_at
                from alerts
                order by id desc
                limit ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
