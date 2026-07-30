"""
SQLite broker data schema, migrations, and cleanup.

Layer: Infrastructure
Depends on: sqlite3 (standard library)
"""

import sqlite3
from pathlib import Path

from src.domain.ports.broker_data_repository import BrokerDataRepositoryError


def connect_sqlite_broker_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_sqlite_broker_schema(db_path: str | Path) -> None:
    _migrate_broker_summaries_if_needed(db_path)
    _migrate_foreign_flow_points_if_needed(db_path)
    _migrate_broker_daily_flow_if_needed(db_path)
    _cleanup_stockbit_summaries_superseded_by_idx(db_path)
    try:
        with connect_sqlite_broker_db(db_path) as conn:
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
            # broker_daily_flow stores Stockbit per-day rows for configured
            # tracked broker codes only. It is not exhaustive full-market
            # broker composition; consumers must name this as tracked-broker
            # flow when exposing it in CLI/JSON.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS broker_daily_flow (
                    ticker          TEXT NOT NULL,
                    date            TEXT NOT NULL,
                    broker_code     TEXT NOT NULL,
                    broker_name     TEXT NOT NULL DEFAULT '',
                    source          TEXT NOT NULL DEFAULT 'stockbit',
                    buy_lot         INTEGER NOT NULL DEFAULT 0,
                    sell_lot        INTEGER NOT NULL DEFAULT 0,
                    net_lot         INTEGER NOT NULL DEFAULT 0,
                    buy_value       TEXT NOT NULL DEFAULT '0',
                    sell_value      TEXT NOT NULL DEFAULT '0',
                    net_value       TEXT NOT NULL DEFAULT '0',
                    avg_buy_price   TEXT NOT NULL DEFAULT '0',
                    avg_sell_price  TEXT NOT NULL DEFAULT '0',
                    avg_price       TEXT NOT NULL DEFAULT '0',
                    buy_pct         REAL NOT NULL DEFAULT 0,
                    sell_pct        REAL NOT NULL DEFAULT 0,
                    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (ticker, date, broker_code, source)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bdf_ticker_date
                ON broker_daily_flow(ticker, date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bdf_ticker_broker
                ON broker_daily_flow(ticker, broker_code, date)
            """)
            # Desk-centric list/show (WHERE broker_code = ? / IN (...))
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bdf_broker_date
                ON broker_daily_flow(broker_code, date)
            """)
            conn.commit()
    except sqlite3.Error as e:
        raise BrokerDataRepositoryError(f"Failed to create schema: {e}") from e


def _migrate_broker_summaries_if_needed(db_path: str | Path) -> None:
    """Rebuild broker_summaries to add source column to PK if not already present."""
    try:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
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


def _migrate_foreign_flow_points_if_needed(db_path: str | Path) -> None:
    """Rename legacy broker_flow_points storage to foreign_flow_points."""
    try:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            old_exists = (
                conn.execute("""
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='broker_flow_points'
                """).fetchone()
                is not None
            )
            new_exists = (
                conn.execute("""
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='foreign_flow_points'
                """).fetchone()
                is not None
            )

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
        raise BrokerDataRepositoryError(f"Failed to migrate foreign_flow_points: {e}") from e


def _migrate_broker_daily_flow_if_needed(db_path: str | Path) -> None:
    """Migrate broker_daily_flow columns/indexes on existing DBs."""
    try:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        try:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='broker_daily_flow'"
            ).fetchone()
            if row is None:
                return  # table doesn't exist yet — ensure_sqlite_broker_schema will create it
            existing_cols = {
                r[1] for r in conn.execute("PRAGMA table_info(broker_daily_flow)").fetchall()
            }
            if "avg_buy_price" not in existing_cols:
                conn.execute(
                    "ALTER TABLE broker_daily_flow "
                    "ADD COLUMN avg_buy_price TEXT NOT NULL DEFAULT '0'"
                )
            if "avg_sell_price" not in existing_cols:
                conn.execute(
                    "ALTER TABLE broker_daily_flow "
                    "ADD COLUMN avg_sell_price TEXT NOT NULL DEFAULT '0'"
                )
            # Desk-centric reads (TUI broker list / show pulse) need broker_code lead.
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_bdf_broker_date
                ON broker_daily_flow(broker_code, date)
            """)
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as e:
        raise BrokerDataRepositoryError(f"Failed to migrate broker_daily_flow: {e}") from e


def _cleanup_stockbit_summaries_superseded_by_idx(db_path: str | Path) -> None:
    """Remove broker_summaries rows with source='stockbit' where an IDX row exists.

    Stockbit broker_summaries have a synthetic total_value (~72% of true turnover).
    IDX rows are accurate. Where both exist for the same ticker+date, the Stockbit
    row is strictly worse and should be removed so IDX data is used exclusively.
    """
    try:
        with connect_sqlite_broker_db(db_path) as conn:
            if (
                conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='broker_summaries'"
                ).fetchone()
                is None
            ):
                return
            conn.execute("""
                DELETE FROM broker_summaries
                WHERE source = 'stockbit'
                  AND EXISTS (
                    SELECT 1 FROM broker_summaries b2
                    WHERE b2.ticker = broker_summaries.ticker
                      AND b2.date   = broker_summaries.date
                      AND b2.source = 'idx'
                  )
            """)
    except sqlite3.Error as e:
        raise BrokerDataRepositoryError(f"Failed to clean up stockbit broker_summaries: {e}") from e
