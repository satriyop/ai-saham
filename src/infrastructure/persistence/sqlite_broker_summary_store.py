"""
SQLite persistence for broker_summaries.

Layer: Infrastructure
Depends on: Domain ports, sqlite3 (standard library)
"""

import sqlite3
from datetime import date
from pathlib import Path

from src.domain.entities.broker_flow import BrokerSummary
from src.domain.ports.broker_data_repository import BrokerDataRepositoryError
from src.infrastructure.persistence.sqlite_broker_row_mappers import (
    row_to_broker_summary,
    serialize_broker_transactions,
)
from src.infrastructure.persistence.sqlite_broker_schema import connect_sqlite_broker_db


class SQLiteBrokerSummaryStore:
    """Persistence for broker_summaries only."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        return connect_sqlite_broker_db(self._db_path)

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
                            serialize_broker_transactions(s.top_buyers),
                            serialize_broker_transactions(s.top_sellers),
                        )
                        for s in summaries
                    ],
                )
                conn.commit()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to save broker summaries: {e}") from e

    def get_broker_summary(self, ticker: str, target_date: date) -> BrokerSummary | None:
        """Return single summary for a date; prefers IDX over Stockbit."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM broker_summaries
                    WHERE ticker = ? AND date = ?
                    ORDER BY source ASC
                    LIMIT 1
                    """,
                    [ticker.upper(), target_date.isoformat()],
                ).fetchone()
            return row_to_broker_summary(row) if row else None
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

        source=None returns one row per date, preferring IDX ('idx' < 'stockbit').
        source='idx'|'stockbit' returns only that source.
        """
        try:
            with self._get_connection() as conn:
                if source is None:
                    query = """
                        SELECT bs.* FROM broker_summaries bs
                        INNER JOIN (
                            SELECT ticker, date, MIN(source) AS best_src
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
            return [row_to_broker_summary(r) for r in rows]
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

    def get_cached_tickers(self) -> list[str]:
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT DISTINCT ticker FROM broker_summaries ORDER BY ticker"
                ).fetchall()
                return [row["ticker"] for row in rows]
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get cached tickers: {e}") from e
