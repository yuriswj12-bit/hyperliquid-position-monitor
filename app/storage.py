import json
from pathlib import Path

import aiosqlite

from datetime import datetime, timezone

from app.models import AccountSnapshot, AlertEvent, PositionChange, WatchedWalletRequest
from app.risk import normalize_snapshot


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
                    created_at text not null,
                    fingerprint text not null
                )
                """
            )
            await self._ensure_column(db, "alerts", "fingerprint", "text")
            await db.execute("create index if not exists idx_snapshots_user_id on snapshots (user, id)")
            await db.execute("create index if not exists idx_alerts_fingerprint_id on alerts (fingerprint, id)")
            await db.execute(
                """
                create table if not exists position_changes (
                    id integer primary key autoincrement,
                    user text not null,
                    coin text not null,
                    change_type text not null,
                    previous_size real not null,
                    current_size real not null,
                    previous_value real not null,
                    current_value real not null,
                    change_percent real,
                    message text not null,
                    created_at text not null
                )
                """
            )
            await db.execute(
                """
                create table if not exists alert_fingerprints (
                    fingerprint text primary key,
                    last_sent_at text not null
                )
                """
            )
            await db.execute(
                """
                create table if not exists watched_wallets (
                    user text primary key,
                    name text,
                    tags text,
                    notes text,
                    created_at text not null,
                    updated_at text not null
                )
                """
            )
            await db.commit()

    async def list_watched_wallets(self) -> list[dict]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                select w.user, w.name, w.tags, w.notes, w.created_at, w.updated_at,
                       count(s.id) as snapshot_count,
                       max(s.captured_at) as latest_snapshot_at
                from watched_wallets w
                left join snapshots s on s.user = w.user
                group by w.user, w.name, w.tags, w.notes, w.created_at, w.updated_at
                order by coalesce(w.name, w.user), w.user
                """
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def upsert_watched_wallet(self, wallet: WatchedWalletRequest) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                insert into watched_wallets (user, name, tags, notes, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                on conflict(user) do update set
                    name = excluded.name,
                    tags = excluded.tags,
                    notes = excluded.notes,
                    updated_at = excluded.updated_at
                """,
                (
                    wallet.user,
                    clean_optional(wallet.name),
                    clean_optional(wallet.tags),
                    clean_optional(wallet.notes),
                    now,
                    now,
                ),
            )
            await db.commit()
        return await self.get_watched_wallet(wallet.user) or {}

    async def get_watched_wallet(self, user: str) -> dict | None:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                select w.user, w.name, w.tags, w.notes, w.created_at, w.updated_at,
                       count(s.id) as snapshot_count,
                       max(s.captured_at) as latest_snapshot_at
                from watched_wallets w
                left join snapshots s on s.user = w.user
                where w.user = ?
                group by w.user, w.name, w.tags, w.notes, w.created_at, w.updated_at
                """,
                (user,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def delete_watched_wallet(self, user: str) -> bool:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute("delete from watched_wallets where user = ?", (user,))
            await db.commit()
            return cursor.rowcount > 0

    async def active_wallet_addresses(self, configured_wallets: list[str]) -> list[str]:
        database_wallets = [wallet["user"] for wallet in await self.list_watched_wallets()]
        return list(dict.fromkeys([*configured_wallets, *database_wallets]))

    async def _ensure_column(self, db: aiosqlite.Connection, table: str, column: str, definition: str) -> None:
        cursor = await db.execute(f"pragma table_info({table})")
        rows = await cursor.fetchall()
        if column not in {row[1] for row in rows}:
            await db.execute(f"alter table {table} add column {column} {definition}")

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
                insert into alerts (user, coin, severity, message, created_at, fingerprint)
                values (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event.user,
                        event.coin,
                        event.severity,
                        event.message,
                        event.created_at.isoformat(),
                        event.fingerprint,
                    )
                    for event in events
                ],
            )
            await db.executemany(
                """
                insert into alert_fingerprints (fingerprint, last_sent_at)
                values (?, ?)
                on conflict(fingerprint) do update set last_sent_at = excluded.last_sent_at
                """,
                [(event.fingerprint, event.created_at.isoformat()) for event in events],
            )
            await db.commit()

    async def recent_alerts(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                select user, coin, severity, message, created_at, fingerprint
                from alerts
                order by id desc
                limit ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def latest_snapshot(self, user: str, liquidation_threshold: float) -> AccountSnapshot | None:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                select raw_json
                from snapshots
                where user = ?
                order by id desc
                limit 1
                """,
                (user,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return normalize_snapshot(user, json.loads(row["raw_json"]), liquidation_threshold)

    async def latest_any_snapshot(self, liquidation_threshold: float) -> AccountSnapshot | None:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                select user, raw_json
                from snapshots
                order by id desc
                limit 1
                """
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return normalize_snapshot(row["user"], json.loads(row["raw_json"]), liquidation_threshold)

    async def largest_position_value_wallet(self) -> dict | None:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                select s.user, s.captured_at, s.account_value, s.total_position_value,
                       s.total_margin_used, s.unrealized_pnl
                from snapshots s
                join (
                    select user, max(id) as latest_id
                    from snapshots
                    group by user
                ) latest on latest.latest_id = s.id
                order by s.total_position_value desc
                limit 1
                """
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def save_position_changes(self, changes: list[PositionChange]) -> None:
        if not changes:
            return
        async with aiosqlite.connect(self.database_path) as db:
            await db.executemany(
                """
                insert into position_changes (
                    user, coin, change_type, previous_size, current_size,
                    previous_value, current_value, change_percent, message, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        change.user,
                        change.coin,
                        change.change_type,
                        change.previous_size,
                        change.current_size,
                        change.previous_value,
                        change.current_value,
                        change.change_percent,
                        change.message,
                        change.created_at.isoformat(),
                    )
                    for change in changes
                ],
            )
            await db.commit()

    async def recent_position_changes(self, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                select user, coin, change_type, previous_size, current_size,
                       previous_value, current_value, change_percent, message, created_at
                from position_changes
                order by id desc
                limit ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def filter_alerts_for_cooldown(
        self,
        events: list[AlertEvent],
        cooldown_seconds: int,
    ) -> list[AlertEvent]:
        if not events or cooldown_seconds <= 0:
            return events

        now = datetime.now(timezone.utc)
        allowed: list[AlertEvent] = []
        async with aiosqlite.connect(self.database_path) as db:
            for event in events:
                cursor = await db.execute(
                    """
                    select last_sent_at
                    from alert_fingerprints
                    where fingerprint = ?
                    """,
                    (event.fingerprint,),
                )
                row = await cursor.fetchone()
                if row is None:
                    allowed.append(event)
                    continue
                last_sent = datetime.fromisoformat(row[0])
                if (now - last_sent).total_seconds() >= cooldown_seconds:
                    allowed.append(event)
        return allowed


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
