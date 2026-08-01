"""Read-only SQLite market candle access for status / readiness paths.

Opens with mode=ro. Never creates files, directories, tables, indexes, or
columns. Never calls schema ensure.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepositoryError


class SQLiteMarketDataReadRepository:
    """Bounded read access to existing candles (no writes, no DDL)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def _connect(self) -> sqlite3.Connection:
        if not self._db_path.exists():
            raise FileNotFoundError(
                f"market database does not exist (status is read-only): {self._db_path}"
            )
        uri = f"file:{self._db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT MIN(date) AS min_date, MAX(date) AS max_date
                    FROM candles
                    WHERE ticker = ?
                    """,
                    [ticker.upper()],
                ).fetchone()
            if not row or not row["min_date"]:
                return None
            return (
                date.fromisoformat(str(row["min_date"])),
                date.fromisoformat(str(row["max_date"])),
            )
        except sqlite3.Error as exc:
            raise MarketDataRepositoryError(f"Failed to get date range: {exc}") from exc

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        try:
            query = "SELECT * FROM candles WHERE ticker = ?"
            params: list[object] = [ticker.upper()]
            if start_date is not None:
                query += " AND date >= ?"
                params.append(start_date.isoformat())
            if end_date is not None:
                query += " AND date <= ?"
                params.append(end_date.isoformat())
            query += " ORDER BY date ASC"
            with self._connect() as conn:
                rows = conn.execute(query, params).fetchall()
            return [self._row_to_candle(row) for row in rows]
        except sqlite3.Error as exc:
            raise MarketDataRepositoryError(f"Failed to get candles: {exc}") from exc

    @staticmethod
    def _row_to_candle(row: sqlite3.Row) -> Candle:
        return Candle(
            ticker=str(row["ticker"]),
            date=date.fromisoformat(str(row["date"])),
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=int(row["volume"]),
        )
