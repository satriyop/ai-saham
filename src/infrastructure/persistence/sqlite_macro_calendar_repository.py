"""
SQLiteMacroCalendarRepository — SQLite persistence for the market-wide
macroeconomic calendar.

Tables: macro_calendar_events, macro_calendar_sync.
Never touches corporate_action_* tables.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from src.application.ports.macro_calendar_repository import MacroCalendarRepository
from src.domain.value_objects.macro_calendar_event import (
    MacroCalendarEvent,
    MacroEventCategory,
)

_SYNC_KEY = "economic"


class SQLiteMacroCalendarRepository(MacroCalendarRepository):
    """Market-wide macro calendar repository using SQLite."""

    def __init__(self, db_path: str | Path, *, initialize_schema: bool = True) -> None:
        self._db_path = Path(db_path).expanduser()
        if initialize_schema:
            self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS macro_calendar_events (
                    source            TEXT NOT NULL DEFAULT 'stockbit',
                    source_event_id   TEXT NOT NULL,
                    event_date        TEXT NOT NULL,
                    event_time        TEXT,
                    timezone          TEXT,
                    category          TEXT NOT NULL,
                    title             TEXT NOT NULL,
                    country           TEXT NOT NULL DEFAULT 'ID',
                    actual            TEXT,
                    previous          TEXT,
                    forecast          TEXT,
                    reference_period  TEXT,
                    raw_payload_json  TEXT NOT NULL,
                    fetched_at        TEXT NOT NULL,
                    created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at        TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source, source_event_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_macro_cal_date
                ON macro_calendar_events(event_date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_macro_cal_category_date
                ON macro_calendar_events(category, event_date)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS macro_calendar_sync (
                    source           TEXT NOT NULL DEFAULT 'stockbit',
                    sync_key         TEXT NOT NULL,
                    synced_for_date  TEXT NOT NULL,
                    fetched_at       TEXT NOT NULL,
                    status           TEXT NOT NULL,
                    PRIMARY KEY (source, sync_key, synced_for_date)
                )
            """)
            conn.commit()

    def save_events(self, events: list[MacroCalendarEvent]) -> None:
        if not events:
            return
        with self._get_connection() as conn:
            for ev in events:
                conn.execute(
                    """
                    INSERT INTO macro_calendar_events (
                        source, source_event_id, event_date, event_time, timezone,
                        category, title, country, actual, previous, forecast,
                        reference_period, raw_payload_json, fetched_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, source_event_id) DO UPDATE SET
                        event_date       = excluded.event_date,
                        event_time       = excluded.event_time,
                        timezone         = excluded.timezone,
                        category         = excluded.category,
                        title            = excluded.title,
                        country          = excluded.country,
                        actual           = excluded.actual,
                        previous         = excluded.previous,
                        forecast         = excluded.forecast,
                        reference_period = excluded.reference_period,
                        raw_payload_json = excluded.raw_payload_json,
                        fetched_at       = excluded.fetched_at,
                        updated_at       = CURRENT_TIMESTAMP
                    """,
                    (
                        ev.source,
                        ev.source_event_id,
                        ev.event_date.isoformat(),
                        ev.event_time,
                        ev.timezone,
                        ev.category.value,
                        ev.title,
                        ev.country,
                        ev.actual,
                        ev.previous,
                        ev.forecast,
                        ev.reference_period,
                        ev.raw_payload_json,
                        ev.fetched_at,
                    ),
                )
            conn.commit()

    def has_synced_for_date(self, sync_date: date, source: str = "stockbit") -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT status FROM macro_calendar_sync
                WHERE source=? AND sync_key=? AND synced_for_date=?
                """,
                (source, _SYNC_KEY, sync_date.isoformat()),
            ).fetchone()
        return bool(row) and row["status"] == "success"

    def mark_synced(
        self,
        sync_date: date,
        status: str,
        source: str = "stockbit",
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO macro_calendar_sync (
                    source, sync_key, synced_for_date, fetched_at, status
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source, sync_key, synced_for_date) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    status     = excluded.status
                """,
                (
                    source,
                    _SYNC_KEY,
                    sync_date.isoformat(),
                    datetime.now().isoformat(),
                    status,
                ),
            )
            conn.commit()

    def get_events_in_window(
        self,
        from_date: date,
        to_date: date,
        categories: tuple[MacroEventCategory, ...] | None = None,
        as_of_fetched_at: str | None = None,
    ) -> list[MacroCalendarEvent]:
        query = """
            SELECT
                source, source_event_id, event_date, event_time, timezone,
                category, title, country, actual, previous, forecast,
                reference_period, raw_payload_json, fetched_at
            FROM macro_calendar_events
            WHERE event_date >= ? AND event_date <= ?
        """
        params: list[object] = [from_date.isoformat(), to_date.isoformat()]

        if categories:
            placeholders = ",".join("?" for _ in categories)
            query += f" AND category IN ({placeholders})"
            params.extend(c.value for c in categories)

        if as_of_fetched_at is not None:
            query += " AND fetched_at <= ?"
            params.append(as_of_fetched_at)

        query += " ORDER BY event_date ASC, source_event_id ASC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_event(row) for row in rows]

    def reclassify_event_categories(
        self,
        category_for_title: Callable[[str], MacroEventCategory],
    ) -> int:
        """Recompute stored categories from titles; return number of rows updated."""
        updated = 0
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT source, source_event_id, title, category
                FROM macro_calendar_events
                """
            ).fetchall()
            for row in rows:
                new_cat = category_for_title(row["title"] or "")
                new_value = new_cat.value
                if new_value == row["category"]:
                    continue
                conn.execute(
                    """
                    UPDATE macro_calendar_events
                    SET category = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE source = ? AND source_event_id = ?
                    """,
                    (new_value, row["source"], row["source_event_id"]),
                )
                updated += 1
            conn.commit()
        return updated

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> MacroCalendarEvent:
        return MacroCalendarEvent(
            source_event_id=row["source_event_id"],
            event_date=date.fromisoformat(row["event_date"]),
            category=MacroEventCategory(row["category"]),
            title=row["title"],
            event_time=row["event_time"],
            timezone=row["timezone"],
            country=row["country"] or "ID",
            actual=row["actual"],
            previous=row["previous"],
            forecast=row["forecast"],
            reference_period=row["reference_period"],
            source=row["source"],
            raw_payload_json=row["raw_payload_json"],
            fetched_at=row["fetched_at"],
        )
