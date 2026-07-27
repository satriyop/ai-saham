"""
SQLite market data repository.

This adapter implements MarketDataRepository using SQLite.
Provides local-first persistence for market data caching.

Layer: Infrastructure
Depends on: Domain ports, sqlite3 (standard library)
"""

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import (
    MarketDataRepository,
    MarketDataRepositoryError,
)


class SQLiteMarketRepository(MarketDataRepository):
    """
    Market data repository using SQLite.

    This repository:
    - Creates database and schema automatically
    - Supports upsert (insert or update)
    - Uses parameterized queries to prevent SQL injection
    - Stores prices as TEXT to preserve Decimal precision

    Schema:
        candles(
            ticker, date, open, high, low, close, volume,
            source, volume_unit, price_adjustment_policy
        )
        Primary key: (ticker, date)
    """

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize SQLite repository.

        Args:
            db_path: Path to SQLite database file.
                     Parent directories are created if needed.
        """
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        """Create tables if they don't exist."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS candles (
                        ticker TEXT NOT NULL,
                        date TEXT NOT NULL,
                        open TEXT NOT NULL,
                        high TEXT NOT NULL,
                        low TEXT NOT NULL,
                        close TEXT NOT NULL,
                        volume INTEGER NOT NULL,
                        source TEXT NOT NULL DEFAULT 'unknown',
                        volume_unit TEXT NOT NULL DEFAULT 'unknown',
                        price_adjustment_policy TEXT NOT NULL DEFAULT 'unknown',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (ticker, date)
                    )
                """)
                self._ensure_metadata_columns(conn)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_candles_ticker_date
                    ON candles(ticker, date)
                """)
                conn.commit()
        except sqlite3.Error as e:
            raise MarketDataRepositoryError(f"Failed to create schema: {e}") from e

    def _ensure_metadata_columns(self, conn: sqlite3.Connection) -> None:
        """Add candle provenance columns to legacy databases."""
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(candles)").fetchall()}
        if "source" not in existing_cols:
            conn.execute("ALTER TABLE candles ADD COLUMN source TEXT NOT NULL DEFAULT 'unknown'")
        if "volume_unit" not in existing_cols:
            conn.execute(
                "ALTER TABLE candles ADD COLUMN volume_unit TEXT NOT NULL DEFAULT 'unknown'"
            )
        if "price_adjustment_policy" not in existing_cols:
            conn.execute(
                "ALTER TABLE candles ADD COLUMN "
                "price_adjustment_policy TEXT NOT NULL DEFAULT 'unknown'"
            )

    def save_candles(
        self,
        candles: list[Candle],
        *,
        source: str = "unknown",
        volume_unit: str = "unknown",
        price_adjustment_policy: str = "unknown",
    ) -> None:
        """
        Save candles to SQLite. Uses upsert to handle duplicates.

        Args:
            candles: List of Candle entities to persist.
            source: Data provider label, e.g. 'yahoo' or 'idx'.
            volume_unit: Unit stored in Candle.volume, e.g. 'shares'.
            price_adjustment_policy: Provider price adjustment policy.

        Raises:
            MarketDataRepositoryError: If save fails.
        """
        if not candles:
            return

        try:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO candles (
                        ticker, date, open, high, low, close, volume,
                        source, volume_unit, price_adjustment_policy
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, date) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        volume = excluded.volume,
                        source = excluded.source,
                        volume_unit = excluded.volume_unit,
                        price_adjustment_policy = excluded.price_adjustment_policy
                    """,
                    [
                        (
                            c.ticker,
                            c.date.isoformat(),
                            str(c.open),
                            str(c.high),
                            str(c.low),
                            str(c.close),
                            c.volume,
                            source,
                            volume_unit,
                            price_adjustment_policy,
                        )
                        for c in candles
                    ],
                )
                conn.commit()
        except sqlite3.Error as e:
            raise MarketDataRepositoryError(f"Failed to save candles: {e}") from e

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        """
        Retrieve candles from SQLite.

        Args:
            ticker: Stock ticker symbol
            start_date: Optional start of date range (inclusive)
            end_date: Optional end of date range (inclusive)

        Returns:
            List of Candle entities, sorted by date ascending.
        """
        try:
            query = "SELECT * FROM candles WHERE ticker = ?"
            params: list = [ticker.upper()]

            if start_date:
                query += " AND date >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND date <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY date ASC"

            with self._get_connection() as conn:
                rows = conn.execute(query, params).fetchall()

            return [self._row_to_candle(row) for row in rows]

        except sqlite3.Error as e:
            raise MarketDataRepositoryError(f"Failed to get candles: {e}") from e

    def get_candle_source(self, ticker: str, on_date: date) -> str | None:
        """Return persisted provider source for one candle date, if available."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT source
                    FROM candles
                    WHERE ticker = ? AND date = ?
                    LIMIT 1
                    """,
                    (ticker.upper(), on_date.isoformat()),
                ).fetchone()
            return str(row["source"]) if row is not None else None
        except sqlite3.Error as e:
            raise MarketDataRepositoryError(f"Failed to get candle source: {e}") from e

    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> bool:
        """
        Check if cache has data for the specified range.

        Uses date range comparison rather than counting rows
        to handle weekends and holidays correctly.
        """
        date_range = self.get_date_range(ticker)
        if not date_range:
            return False

        cached_start, cached_end = date_range
        return cached_start <= start_date and cached_end >= end_date

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        """
        Get the date range of cached data for a ticker.

        Returns:
            Tuple of (earliest_date, latest_date) or None if no data.
        """
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT MIN(date) as min_date, MAX(date) as max_date
                    FROM candles
                    WHERE ticker = ?
                    """,
                    [ticker.upper()],
                ).fetchone()

            if not row or not row["min_date"]:
                return None

            return (
                date.fromisoformat(row["min_date"]),
                date.fromisoformat(row["max_date"]),
            )

        except sqlite3.Error as e:
            raise MarketDataRepositoryError(f"Failed to get date range: {e}") from e

    def list_tickers(self) -> list[str]:
        """Return the distinct tickers with cached candles, sorted ascending.

        Implements the ``CachedTickerCatalog`` application port for offline
        ticker-search autocomplete.
        """
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT ticker FROM candles ORDER BY ticker ASC"
                ).fetchall()
            return [row["ticker"] for row in rows]
        except sqlite3.Error as e:
            raise MarketDataRepositoryError(f"Failed to list tickers: {e}") from e

    def _row_to_candle(self, row: sqlite3.Row) -> Candle:
        """Convert database row to Candle entity."""
        open_val = Decimal(row["open"])
        high_val = Decimal(row["high"])
        low_val = Decimal(row["low"])
        close_val = Decimal(row["close"])

        # Sanitize legacy high/low anomalies gracefully
        sanitized_high = max(open_val, high_val, close_val, low_val)
        sanitized_low = min(open_val, low_val, close_val, high_val)

        return Candle(
            ticker=row["ticker"],
            date=date.fromisoformat(row["date"]),
            open=open_val,
            high=sanitized_high,
            low=sanitized_low,
            close=close_val,
            volume=row["volume"],
        )
