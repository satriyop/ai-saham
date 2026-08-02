"""
SQLiteCorporateActionCalendarRepository — SQLite persistence for the market-wide
corporate action calendar.

Stores events in `corporate_action_events`, their dated milestones in
`corporate_action_event_dates`, and sync markers in
`corporate_action_calendar_sync`. This repository owns SQLite only; it makes no
fetch/freshness policy decisions (that is the use case's job).

Distinct from the per-ticker corp_action_cache system, which it never touches.

Layer: Infrastructure
Depends on: Application ports, domain value objects, sqlite3 (standard library)
"""

import json
import sqlite3
from datetime import date
from pathlib import Path

from src.application.ports.corporate_action_calendar_repository import (
    CorporateActionCalendarRepository,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)


def _sync_key(event_types: tuple[CorporateActionType, ...]) -> str:
    """Canonical sync key: sorted, comma-joined `.value` strings."""
    return ",".join(sorted(et.value for et in event_types))


class SQLiteCorporateActionCalendarRepository(CorporateActionCalendarRepository):
    """Market-wide corporate action calendar repository using SQLite."""

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
                CREATE TABLE IF NOT EXISTS corporate_action_events (
                    source                  TEXT NOT NULL DEFAULT 'stockbit',
                    event_type              TEXT NOT NULL,
                    source_event_id         TEXT NOT NULL,
                    ticker                  TEXT NOT NULL,
                    company_id              TEXT,
                    company_name            TEXT,
                    active                  INTEGER NOT NULL,
                    event_note              TEXT,
                    amount_value            TEXT,
                    amount_currency         TEXT,
                    ratio_old               TEXT,
                    ratio_new               TEXT,
                    price                   TEXT,
                    raw_payload_json        TEXT NOT NULL,
                    fetched_at              TEXT NOT NULL,
                    created_at              TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at              TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (source, event_type, source_event_id, ticker)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corporate_action_event_dates (
                    source                  TEXT NOT NULL DEFAULT 'stockbit',
                    event_type              TEXT NOT NULL,
                    source_event_id         TEXT NOT NULL,
                    ticker                  TEXT NOT NULL,
                    date_role               TEXT NOT NULL,
                    event_date              TEXT NOT NULL,
                    event_time              TEXT,
                    timezone                TEXT,
                    fetched_at              TEXT NOT NULL,
                    PRIMARY KEY (source, event_type, source_event_id, ticker, date_role)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_corp_calendar_ticker_date
                ON corporate_action_event_dates(ticker, event_date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_corp_calendar_date_role
                ON corporate_action_event_dates(event_date, date_role)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_corp_calendar_type_date
                ON corporate_action_event_dates(event_type, event_date)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS corporate_action_calendar_sync (
                    source           TEXT NOT NULL DEFAULT 'stockbit',
                    sync_key         TEXT NOT NULL,
                    synced_for_date  TEXT NOT NULL,
                    fetched_at       TEXT NOT NULL,
                    event_types_json TEXT NOT NULL,
                    status           TEXT NOT NULL,
                    PRIMARY KEY (source, sync_key, synced_for_date)
                )
            """)
            conn.commit()

    # ── Save ────────────────────────────────────────────────────────────────

    def save_events(self, events: list[CorporateActionCalendarEvent]) -> None:
        if not events:
            return
        with self._get_connection() as conn:
            for ev in events:
                conn.execute(
                    """
                    INSERT INTO corporate_action_events (
                        source, event_type, source_event_id, ticker,
                        company_id, company_name, active, event_note,
                        amount_value, amount_currency, ratio_old, ratio_new,
                        price, raw_payload_json, fetched_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, event_type, source_event_id, ticker) DO UPDATE SET
                        company_id      = excluded.company_id,
                        company_name    = excluded.company_name,
                        active          = excluded.active,
                        event_note      = excluded.event_note,
                        amount_value    = excluded.amount_value,
                        amount_currency = excluded.amount_currency,
                        ratio_old       = excluded.ratio_old,
                        ratio_new       = excluded.ratio_new,
                        price           = excluded.price,
                        raw_payload_json= excluded.raw_payload_json,
                        fetched_at      = excluded.fetched_at,
                        updated_at      = CURRENT_TIMESTAMP
                    """,
                    (
                        ev.source,
                        ev.event_type.value,
                        ev.source_event_id,
                        ev.ticker,
                        ev.company_id,
                        ev.company_name,
                        1 if ev.active else 0,
                        ev.event_note,
                        ev.amount_value,
                        ev.amount_currency,
                        ev.ratio_old,
                        ev.ratio_new,
                        ev.price,
                        ev.raw_payload_json,
                        ev.fetched_at,
                    ),
                )
                # Replace date-role rows for this event only (never touch others).
                conn.execute(
                    """
                    DELETE FROM corporate_action_event_dates
                    WHERE source=? AND event_type=? AND source_event_id=? AND ticker=?
                    """,
                    (ev.source, ev.event_type.value, ev.source_event_id, ev.ticker),
                )
                for d in ev.dates:
                    conn.execute(
                        """
                        INSERT INTO corporate_action_event_dates (
                            source, event_type, source_event_id, ticker,
                            date_role, event_date, event_time, timezone, fetched_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ev.source,
                            ev.event_type.value,
                            ev.source_event_id,
                            ev.ticker,
                            d.date_role.value,
                            d.event_date.isoformat(),
                            d.event_time,
                            d.timezone,
                            ev.fetched_at,
                        ),
                    )
            conn.commit()

    # ── Sync markers ────────────────────────────────────────────────────────

    def has_synced_for_date(
        self,
        sync_date: date,
        event_types: tuple[CorporateActionType, ...],
        source: str = "stockbit",
    ) -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT status FROM corporate_action_calendar_sync
                WHERE source=? AND sync_key=? AND synced_for_date=?
                """,
                (source, _sync_key(event_types), sync_date.isoformat()),
            ).fetchone()
        return bool(row) and row["status"] == "success"

    def has_any_sync_marker(self, source: str = "stockbit") -> bool:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM corporate_action_calendar_sync
                WHERE source=? AND status='success'
                LIMIT 1
                """,
                (source,),
            ).fetchone()
        return row is not None

    def mark_synced(
        self,
        sync_date: date,
        event_types: tuple[CorporateActionType, ...],
        status: str,
        source: str = "stockbit",
    ) -> None:
        from datetime import datetime

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO corporate_action_calendar_sync (
                    source, sync_key, synced_for_date,
                    fetched_at, event_types_json, status
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, sync_key, synced_for_date) DO UPDATE SET
                    fetched_at       = excluded.fetched_at,
                    event_types_json = excluded.event_types_json,
                    status           = excluded.status
                """,
                (
                    source,
                    _sync_key(event_types),
                    sync_date.isoformat(),
                    datetime.now().isoformat(),
                    json.dumps(sorted(et.value for et in event_types)),
                    status,
                ),
            )
            conn.commit()

    # ── Queries ─────────────────────────────────────────────────────────────

    # An event may have date rows both inside and outside the query window. The
    # match predicate (EXISTS subquery `m`) decides which EVENTS qualify, while
    # the outer join to `d` pulls ALL of a matching event's date rows so the
    # reconstructed event is complete (never a partial event with only the
    # single date row that happened to match the filter).
    _SELECT_JOINED = """
        SELECT
            e.source            AS source,
            e.event_type        AS event_type,
            e.source_event_id   AS source_event_id,
            e.ticker            AS ticker,
            e.company_id        AS company_id,
            e.company_name      AS company_name,
            e.active            AS active,
            e.event_note        AS event_note,
            e.amount_value      AS amount_value,
            e.amount_currency   AS amount_currency,
            e.ratio_old         AS ratio_old,
            e.ratio_new         AS ratio_new,
            e.price             AS price,
            e.raw_payload_json  AS raw_payload_json,
            e.fetched_at        AS fetched_at,
            d.date_role         AS date_role,
            d.event_date        AS event_date,
            d.event_time        AS event_time,
            d.timezone          AS timezone
        FROM corporate_action_events e
        JOIN corporate_action_event_dates d
            ON e.source = d.source
           AND e.event_type = d.event_type
           AND e.source_event_id = d.source_event_id
           AND e.ticker = d.ticker
        WHERE EXISTS (
            SELECT 1 FROM corporate_action_event_dates m
            WHERE m.source = e.source
              AND m.event_type = e.event_type
              AND m.source_event_id = e.source_event_id
              AND m.ticker = e.ticker
    """

    def get_events_for_ticker(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
        event_types: tuple[CorporateActionType, ...] | None = None,
        as_of_fetched_at: str | None = None,
    ) -> list[CorporateActionCalendarEvent]:
        query = self._SELECT_JOINED + " AND m.ticker = ? AND m.event_date BETWEEN ? AND ?"
        params: list = [ticker.upper(), from_date.isoformat(), to_date.isoformat()]
        return self._finish_and_run(query, params, event_types, as_of_fetched_at)

    def get_events_for_universe(
        self,
        tickers: tuple[str, ...],
        from_date: date,
        to_date: date,
        event_types: tuple[CorporateActionType, ...] | None = None,
        as_of_fetched_at: str | None = None,
    ) -> list[CorporateActionCalendarEvent]:
        if not tickers:
            return []
        placeholders = ",".join("?" * len(tickers))
        query = (
            self._SELECT_JOINED
            + f" AND m.ticker IN ({placeholders}) AND m.event_date BETWEEN ? AND ?"
        )
        params: list = [t.upper() for t in tickers]
        params += [from_date.isoformat(), to_date.isoformat()]
        return self._finish_and_run(query, params, event_types, as_of_fetched_at)

    def get_events_by_date_role(
        self,
        from_date: date,
        to_date: date,
        date_roles: tuple[CorporateActionDateRole, ...],
        event_types: tuple[CorporateActionType, ...] | None = None,
        as_of_fetched_at: str | None = None,
    ) -> list[CorporateActionCalendarEvent]:
        if not date_roles:
            return []
        role_placeholders = ",".join("?" * len(date_roles))
        query = (
            self._SELECT_JOINED
            + f" AND m.date_role IN ({role_placeholders}) AND m.event_date BETWEEN ? AND ?"
        )
        params: list = [r.value for r in date_roles]
        params += [from_date.isoformat(), to_date.isoformat()]
        return self._finish_and_run(query, params, event_types, as_of_fetched_at)

    # ── Reconstruction helpers ──────────────────────────────────────────────

    def _finish_and_run(
        self,
        query: str,
        params: list,
        event_types: tuple[CorporateActionType, ...] | None,
        as_of_fetched_at: str | None = None,
    ) -> list[CorporateActionCalendarEvent]:
        # Close the EXISTS subquery, apply the optional event-type filter on the
        # outer event row, then run.
        query += ")"
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            query += f" AND e.event_type IN ({placeholders})"
            params += [et.value for et in event_types]
        if as_of_fetched_at is not None:
            # DQ-002G: exclude events/date-rows synced after the decision
            # timestamp. `e`/`d` are the outer event/date-row aliases (in
            # scope here, unlike `m`, which only exists inside the EXISTS
            # subquery closed above). `save_events()` always writes
            # `d.fetched_at == e.fetched_at` for a given event, so the two
            # checks are currently redundant, but both are asserted
            # explicitly rather than relying on that invariant silently.
            query += " AND e.fetched_at <= ? AND d.fetched_at <= ?"
            params += [as_of_fetched_at, as_of_fetched_at]
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return self._rows_to_events(rows)

    @staticmethod
    def _rows_to_events(
        rows: list[sqlite3.Row],
    ) -> list[CorporateActionCalendarEvent]:
        """Group joined rows by event PK into events with nested date tuples.

        One event may have multiple date rows; collect all of an event's
        CorporateActionCalendarDate rows before building the event object.
        """
        grouped: dict[tuple, dict] = {}
        order: list[tuple] = []
        for row in rows:
            key = (
                row["source"],
                row["event_type"],
                row["source_event_id"],
                row["ticker"],
            )
            if key not in grouped:
                grouped[key] = {"row": row, "dates": []}
                order.append(key)
            grouped[key]["dates"].append(
                CorporateActionCalendarDate(
                    date_role=CorporateActionDateRole(row["date_role"]),
                    event_date=date.fromisoformat(row["event_date"]),
                    event_time=row["event_time"],
                    timezone=row["timezone"],
                )
            )

        events: list[CorporateActionCalendarEvent] = []
        for key in order:
            row = grouped[key]["row"]
            dates = tuple(grouped[key]["dates"])
            events.append(
                CorporateActionCalendarEvent(
                    event_type=CorporateActionType(row["event_type"]),
                    source_event_id=row["source_event_id"],
                    ticker=row["ticker"],
                    dates=dates,
                    source=row["source"],
                    company_id=row["company_id"],
                    company_name=row["company_name"],
                    active=bool(row["active"]),
                    event_note=row["event_note"],
                    amount_value=row["amount_value"],
                    amount_currency=row["amount_currency"],
                    ratio_old=row["ratio_old"],
                    ratio_new=row["ratio_new"],
                    price=row["price"],
                    raw_payload_json=row["raw_payload_json"],
                    fetched_at=row["fetched_at"],
                )
            )
        return events
