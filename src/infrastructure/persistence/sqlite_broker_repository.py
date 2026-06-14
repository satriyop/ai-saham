"""
SQLite broker data repository.

This adapter implements BrokerDataRepository using SQLite.
Provides local-first persistence for broker flow data caching.

Layer: Infrastructure
Depends on: Domain ports, sqlite3 (standard library)
"""

import json
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.entities.broker_flow import (
    BrokerFlowPoint,
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)
from src.domain.ports.broker_data_repository import (
    BrokerDataRepository,
    BrokerDataRepositoryError,
)


class SQLiteBrokerRepository(BrokerDataRepository):
    """
    Broker data repository using SQLite.

    Schema:
        broker_summaries(ticker, date, source, ...) PK (ticker, date, source)
        foreign_flow_points(ticker, date, source, ...) PK (ticker, date, source)
        foreign_flow_snapshots(ticker, snapshot_date, period_days, source) PK composite
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        try:
            self._migrate_broker_summaries_if_needed()
            self._migrate_foreign_flow_points_if_needed()
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS broker_summaries (
                        ticker             TEXT NOT NULL,
                        date               TEXT NOT NULL,
                        source             TEXT NOT NULL DEFAULT 'idx',
                        foreign_buy_value  TEXT NOT NULL,
                        foreign_sell_value TEXT NOT NULL,
                        foreign_buy_lot    INTEGER NOT NULL,
                        foreign_sell_lot   INTEGER NOT NULL,
                        total_value        TEXT NOT NULL,
                        total_lot          INTEGER NOT NULL,
                        top_buyers_json    TEXT,
                        top_sellers_json   TEXT,
                        created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (ticker, date, source)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_broker_summaries_ticker_date
                    ON broker_summaries(ticker, date)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS foreign_flow_points (
                        ticker     TEXT NOT NULL,
                        date       TEXT NOT NULL,
                        source     TEXT NOT NULL,
                        net_val    TEXT NOT NULL,
                        net_lot    INTEGER NOT NULL,
                        avg_price  TEXT NOT NULL DEFAULT '0',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (ticker, date, source)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ffp_ticker_source_date
                    ON foreign_flow_points(ticker, source, date)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS foreign_flow_snapshots (
                        ticker        TEXT NOT NULL,
                        snapshot_date TEXT NOT NULL,
                        period_days   INTEGER NOT NULL,
                        source        TEXT NOT NULL DEFAULT 'stockbit',
                        net_val       TEXT NOT NULL,
                        net_lot       INTEGER NOT NULL,
                        created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (ticker, snapshot_date, period_days, source)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ffs_date_period
                    ON foreign_flow_snapshots(snapshot_date, period_days, source)
                """)
                conn.commit()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to create schema: {e}") from e

    def _migrate_broker_summaries_if_needed(self) -> None:
        """Rebuild broker_summaries to add source column to PK if not already present."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path))
            try:
                row = conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='broker_summaries'"
                ).fetchone()
                if row is None or "source" in row[0]:
                    return  # table doesn't exist yet OR already migrated
                conn.executescript("""
                    CREATE TABLE broker_summaries_new (
                        ticker             TEXT NOT NULL,
                        date               TEXT NOT NULL,
                        source             TEXT NOT NULL DEFAULT 'idx',
                        foreign_buy_value  TEXT NOT NULL,
                        foreign_sell_value TEXT NOT NULL,
                        foreign_buy_lot    INTEGER NOT NULL,
                        foreign_sell_lot   INTEGER NOT NULL,
                        total_value        TEXT NOT NULL,
                        total_lot          INTEGER NOT NULL,
                        top_buyers_json    TEXT,
                        top_sellers_json   TEXT,
                        created_at         TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (ticker, date, source)
                    );
                    INSERT INTO broker_summaries_new
                        SELECT ticker, date, 'idx',
                               foreign_buy_value, foreign_sell_value,
                               foreign_buy_lot, foreign_sell_lot,
                               total_value, total_lot,
                               top_buyers_json, top_sellers_json,
                               created_at
                        FROM broker_summaries;
                    DROP TABLE broker_summaries;
                    ALTER TABLE broker_summaries_new RENAME TO broker_summaries;
                """)
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to migrate broker_summaries: {e}") from e

    def _migrate_foreign_flow_points_if_needed(self) -> None:
        """Rename legacy broker_flow_points storage to foreign_flow_points."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path))
            try:
                old_exists = conn.execute(
                    """
                    SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='broker_flow_points'
                    """
                ).fetchone() is not None
                new_exists = conn.execute(
                    """
                    SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='foreign_flow_points'
                    """
                ).fetchone() is not None

                if not old_exists:
                    return

                if not new_exists:
                    conn.executescript("""
                        ALTER TABLE broker_flow_points RENAME TO foreign_flow_points;
                        CREATE INDEX IF NOT EXISTS idx_ffp_ticker_source_date
                        ON foreign_flow_points(ticker, source, date);
                    """)
                    conn.commit()
                    return

                conn.executescript("""
                    INSERT OR REPLACE INTO foreign_flow_points
                        (ticker, date, source, net_val, net_lot, avg_price, created_at)
                    SELECT ticker, date, source, net_val, net_lot, avg_price, created_at
                    FROM broker_flow_points;
                    DROP TABLE broker_flow_points;
                    CREATE INDEX IF NOT EXISTS idx_ffp_ticker_source_date
                    ON foreign_flow_points(ticker, source, date);
                """)
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(
                f"Failed to migrate foreign_flow_points: {e}"
            ) from e

    # ── Serialization helpers ──────────────────────────────────────────────

    def _serialize_transactions(self, transactions: tuple[BrokerTransaction, ...]) -> str:
        return json.dumps([t.to_dict() for t in transactions])

    def _deserialize_transactions(self, json_str: str | None) -> tuple[BrokerTransaction, ...]:
        if not json_str:
            return ()
        return tuple(BrokerTransaction.from_dict(d) for d in json.loads(json_str))

    def _row_to_summary(self, row: sqlite3.Row) -> BrokerSummary:
        return BrokerSummary(
            ticker=row["ticker"],
            date=date.fromisoformat(row["date"]),
            top_buyers=self._deserialize_transactions(row["top_buyers_json"]),
            top_sellers=self._deserialize_transactions(row["top_sellers_json"]),
            foreign_buy_value=Decimal(row["foreign_buy_value"]),
            foreign_sell_value=Decimal(row["foreign_sell_value"]),
            foreign_buy_lot=row["foreign_buy_lot"],
            foreign_sell_lot=row["foreign_sell_lot"],
            total_value=Decimal(row["total_value"]),
            total_lot=row["total_lot"],
            source=row["source"],
        )

    # ── BrokerSummary persistence ──────────────────────────────────────────

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        self.save_broker_summaries([summary])

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        if not summaries:
            return
        try:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO broker_summaries (
                        ticker, date, source,
                        foreign_buy_value, foreign_sell_value,
                        foreign_buy_lot, foreign_sell_lot,
                        total_value, total_lot,
                        top_buyers_json, top_sellers_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, date, source) DO UPDATE SET
                        foreign_buy_value  = excluded.foreign_buy_value,
                        foreign_sell_value = excluded.foreign_sell_value,
                        foreign_buy_lot    = excluded.foreign_buy_lot,
                        foreign_sell_lot   = excluded.foreign_sell_lot,
                        total_value        = excluded.total_value,
                        total_lot          = excluded.total_lot,
                        top_buyers_json    = excluded.top_buyers_json,
                        top_sellers_json   = excluded.top_sellers_json
                    """,
                    [
                        (
                            s.ticker.upper(),
                            s.date.isoformat(),
                            s.source,
                            str(s.foreign_buy_value),
                            str(s.foreign_sell_value),
                            s.foreign_buy_lot,
                            s.foreign_sell_lot,
                            str(s.total_value),
                            s.total_lot,
                            self._serialize_transactions(s.top_buyers),
                            self._serialize_transactions(s.top_sellers),
                        )
                        for s in summaries
                    ],
                )
                conn.commit()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to save broker summaries: {e}") from e

    def get_broker_summary(self, ticker: str, target_date: date) -> BrokerSummary | None:
        """Return single summary for a date; prefers Stockbit over IDX."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM broker_summaries
                    WHERE ticker = ? AND date = ?
                    ORDER BY source DESC
                    LIMIT 1
                    """,
                    [ticker.upper(), target_date.isoformat()],
                ).fetchone()
            return self._row_to_summary(row) if row else None
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get broker summary: {e}") from e

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[BrokerSummary]:
        """
        Retrieve summaries in date range.

        source=None returns one row per date, preferring Stockbit ('stockbit' > 'idx').
        source='idx'|'stockbit' returns only that source.
        """
        try:
            with self._get_connection() as conn:
                if source is None:
                    query = """
                        SELECT bs.* FROM broker_summaries bs
                        INNER JOIN (
                            SELECT ticker, date, MAX(source) AS best_src
                            FROM broker_summaries
                            WHERE ticker = ?
                    """
                    params: list = [ticker.upper()]
                    if start_date:
                        query += " AND date >= ?"
                        params.append(start_date.isoformat())
                    if end_date:
                        query += " AND date <= ?"
                        params.append(end_date.isoformat())
                    query += """
                            GROUP BY ticker, date
                        ) best ON bs.ticker = best.ticker
                               AND bs.date = best.date
                               AND bs.source = best.best_src
                        ORDER BY bs.date ASC
                    """
                else:
                    query = "SELECT * FROM broker_summaries WHERE ticker = ? AND source = ?"
                    params = [ticker.upper(), source]
                    if start_date:
                        query += " AND date >= ?"
                        params.append(start_date.isoformat())
                    if end_date:
                        query += " AND date <= ?"
                        params.append(end_date.isoformat())
                    query += " ORDER BY date ASC"

                rows = conn.execute(query, params).fetchall()
            return [self._row_to_summary(r) for r in rows]
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get broker summaries: {e}") from e

    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        source: str | None = None,
    ) -> bool:
        date_range = self.get_date_range(ticker, source=source)
        if not date_range:
            return False
        cached_start, cached_end = date_range
        return cached_start <= start_date and cached_end >= end_date

    def get_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        try:
            with self._get_connection() as conn:
                if source is None:
                    row = conn.execute(
                        """
                        SELECT MIN(date) AS min_date, MAX(date) AS max_date
                        FROM broker_summaries WHERE ticker = ?
                        """,
                        [ticker.upper()],
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT MIN(date) AS min_date, MAX(date) AS max_date
                        FROM broker_summaries WHERE ticker = ? AND source = ?
                        """,
                        [ticker.upper(), source],
                    ).fetchone()
            if not row or not row["min_date"]:
                return None
            return (
                date.fromisoformat(row["min_date"]),
                date.fromisoformat(row["max_date"]),
            )
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get date range: {e}") from e

    # ── ForeignFlowPoint persistence ───────────────────────────────────────

    def save_foreign_flow_points(self, points: list[ForeignFlowPoint]) -> None:
        if not points:
            return
        try:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO foreign_flow_points (ticker, date, source, net_val, net_lot, avg_price)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, date, source) DO UPDATE SET
                        net_val   = excluded.net_val,
                        net_lot   = excluded.net_lot,
                        avg_price = excluded.avg_price
                    """,
                    [
                        (
                            p.ticker.upper(),
                            p.date.isoformat(),
                            p.source,
                            str(p.net_val),
                            p.net_lot,
                            str(p.avg_price),
                        )
                        for p in points
                    ],
                )
                conn.commit()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to save foreign flow points: {e}") from e

    def get_foreign_flow_points(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[ForeignFlowPoint]:
        """
        Return aggregate foreign flow points. source=None returns one per date,
        preferring Stockbit.
        """
        try:
            with self._get_connection() as conn:
                if source is None:
                    query = """
                        SELECT bfp.* FROM foreign_flow_points bfp
                        INNER JOIN (
                            SELECT ticker, date, MAX(source) AS best_src
                            FROM foreign_flow_points WHERE ticker = ?
                    """
                    params: list = [ticker.upper()]
                    if start_date:
                        query += " AND date >= ?"
                        params.append(start_date.isoformat())
                    if end_date:
                        query += " AND date <= ?"
                        params.append(end_date.isoformat())
                    query += """
                            GROUP BY ticker, date
                        ) best ON bfp.ticker = best.ticker
                               AND bfp.date = best.date
                               AND bfp.source = best.best_src
                        ORDER BY bfp.date ASC
                    """
                else:
                    query = "SELECT * FROM foreign_flow_points WHERE ticker = ? AND source = ?"
                    params = [ticker.upper(), source]
                    if start_date:
                        query += " AND date >= ?"
                        params.append(start_date.isoformat())
                    if end_date:
                        query += " AND date <= ?"
                        params.append(end_date.isoformat())
                    query += " ORDER BY date ASC"

                rows = conn.execute(query, params).fetchall()
            return [
                ForeignFlowPoint(
                    ticker=r["ticker"],
                    date=date.fromisoformat(r["date"]),
                    net_val=Decimal(r["net_val"]),
                    net_lot=r["net_lot"],
                    avg_price=Decimal(r["avg_price"]),
                    source=r["source"],
                )
                for r in rows
            ]
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get foreign flow points: {e}") from e

    def get_foreign_flow_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        """Get the date range of stored daily aggregate foreign flow points."""
        try:
            with self._get_connection() as conn:
                if source is None:
                    row = conn.execute(
                        """
                        SELECT MIN(date) AS min_date, MAX(date) AS max_date
                        FROM foreign_flow_points WHERE ticker = ?
                        """,
                        [ticker.upper()],
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT MIN(date) AS min_date, MAX(date) AS max_date
                        FROM foreign_flow_points WHERE ticker = ? AND source = ?
                        """,
                        [ticker.upper(), source],
                    ).fetchone()
            if not row or not row["min_date"]:
                return None
            return (
                date.fromisoformat(row["min_date"]),
                date.fromisoformat(row["max_date"]),
            )
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get foreign flow date range: {e}") from e

    def save_broker_flow_points(self, points: list[BrokerFlowPoint]) -> None:
        """Deprecated alias for save_foreign_flow_points."""
        self.save_foreign_flow_points(points)

    def get_broker_flow_points(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str | None = None,
    ) -> list[BrokerFlowPoint]:
        """Deprecated alias for get_foreign_flow_points."""
        return self.get_foreign_flow_points(ticker, start_date, end_date, source)

    def get_broker_flow_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        """Deprecated alias for get_foreign_flow_date_range."""
        return self.get_foreign_flow_date_range(ticker, source=source)

    # ── ForeignFlowSnapshot persistence ───────────────────────────────────

    def save_foreign_flow_snapshots(
        self,
        snapshots: list[ForeignFlowSnapshot],
        snapshot_date: date,
        period_days: int,
    ) -> None:
        if not snapshots:
            return
        try:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO foreign_flow_snapshots
                        (ticker, snapshot_date, period_days, source, net_val, net_lot)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, snapshot_date, period_days, source) DO UPDATE SET
                        net_val = excluded.net_val,
                        net_lot = excluded.net_lot
                    """,
                    [
                        (
                            s.ticker.upper(),
                            snapshot_date.isoformat(),
                            period_days,
                            "stockbit",
                            str(s.net_val),
                            s.net_lot,
                        )
                        for s in snapshots
                    ],
                )
                conn.commit()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to save foreign flow snapshots: {e}") from e

    def get_foreign_flow_snapshots(
        self,
        snapshot_date: date,
        period_days: int,
    ) -> list[ForeignFlowSnapshot]:
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT ticker, snapshot_date, net_val, net_lot
                    FROM foreign_flow_snapshots
                    WHERE snapshot_date = ? AND period_days = ?
                    ORDER BY CAST(net_val AS REAL) DESC
                    """,
                    [snapshot_date.isoformat(), period_days],
                ).fetchall()
            return [
                ForeignFlowSnapshot(
                    ticker=r["ticker"],
                    date=date.fromisoformat(r["snapshot_date"]),
                    net_val=Decimal(r["net_val"]),
                    net_lot=r["net_lot"],
                )
                for r in rows
            ]
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get foreign flow snapshots: {e}") from e
