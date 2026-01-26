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
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
)
from src.domain.ports.broker_data_repository import (
    BrokerDataRepository,
    BrokerDataRepositoryError,
)


class SQLiteBrokerRepository(BrokerDataRepository):
    """
    Broker data repository using SQLite.

    This repository:
    - Creates database and schema automatically
    - Supports upsert (insert or update)
    - Uses parameterized queries to prevent SQL injection
    - Stores broker transactions as JSON for flexibility

    Schema:
        broker_summaries(ticker, date, foreign_*, total_*, top_buyers_json, top_sellers_json)
        Primary key: (ticker, date)
    """

    def __init__(self, db_path: str | Path) -> None:
        """
        Initialize SQLite repository.

        Args:
            db_path: Path to SQLite database file.
                     Can be same file as market data or separate.
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
                    CREATE TABLE IF NOT EXISTS broker_summaries (
                        ticker TEXT NOT NULL,
                        date TEXT NOT NULL,
                        foreign_buy_value TEXT NOT NULL,
                        foreign_sell_value TEXT NOT NULL,
                        foreign_buy_lot INTEGER NOT NULL,
                        foreign_sell_lot INTEGER NOT NULL,
                        total_value TEXT NOT NULL,
                        total_lot INTEGER NOT NULL,
                        top_buyers_json TEXT,
                        top_sellers_json TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (ticker, date)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_broker_summaries_ticker_date
                    ON broker_summaries(ticker, date)
                """)
                conn.commit()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to create schema: {e}") from e

    def _serialize_transactions(
        self, transactions: tuple[BrokerTransaction, ...]
    ) -> str:
        """Serialize broker transactions to JSON."""
        return json.dumps([t.to_dict() for t in transactions])

    def _deserialize_transactions(
        self, json_str: str | None
    ) -> tuple[BrokerTransaction, ...]:
        """Deserialize broker transactions from JSON."""
        if not json_str:
            return ()
        data = json.loads(json_str)
        return tuple(BrokerTransaction.from_dict(d) for d in data)

    def save_broker_summary(self, summary: BrokerSummary) -> None:
        """Save a broker summary to SQLite."""
        self.save_broker_summaries([summary])

    def save_broker_summaries(self, summaries: list[BrokerSummary]) -> None:
        """Save multiple broker summaries to SQLite."""
        if not summaries:
            return

        try:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO broker_summaries (
                        ticker, date,
                        foreign_buy_value, foreign_sell_value,
                        foreign_buy_lot, foreign_sell_lot,
                        total_value, total_lot,
                        top_buyers_json, top_sellers_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, date) DO UPDATE SET
                        foreign_buy_value = excluded.foreign_buy_value,
                        foreign_sell_value = excluded.foreign_sell_value,
                        foreign_buy_lot = excluded.foreign_buy_lot,
                        foreign_sell_lot = excluded.foreign_sell_lot,
                        total_value = excluded.total_value,
                        total_lot = excluded.total_lot,
                        top_buyers_json = excluded.top_buyers_json,
                        top_sellers_json = excluded.top_sellers_json
                    """,
                    [
                        (
                            s.ticker.upper(),
                            s.date.isoformat(),
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

    def get_broker_summary(
        self,
        ticker: str,
        target_date: date,
    ) -> BrokerSummary | None:
        """Retrieve a broker summary for a specific date."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM broker_summaries
                    WHERE ticker = ? AND date = ?
                    """,
                    [ticker.upper(), target_date.isoformat()],
                ).fetchone()

            if not row:
                return None

            return self._row_to_summary(row)

        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get broker summary: {e}") from e

    def get_broker_summaries(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[BrokerSummary]:
        """Retrieve broker summaries within a date range."""
        try:
            query = "SELECT * FROM broker_summaries WHERE ticker = ?"
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

            return [self._row_to_summary(row) for row in rows]

        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get broker summaries: {e}") from e

    def has_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> bool:
        """Check if repository has data for the specified range."""
        date_range = self.get_date_range(ticker)
        if not date_range:
            return False

        cached_start, cached_end = date_range
        return cached_start <= start_date and cached_end >= end_date

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        """Get the date range of stored data for a ticker."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT MIN(date) as min_date, MAX(date) as max_date
                    FROM broker_summaries
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
            raise BrokerDataRepositoryError(f"Failed to get date range: {e}") from e

    def _row_to_summary(self, row: sqlite3.Row) -> BrokerSummary:
        """Convert database row to BrokerSummary entity."""
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
        )
