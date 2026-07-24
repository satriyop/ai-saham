"""
SQLite persistence for broker_daily_flow.

Layer: Infrastructure
Depends on: Domain ports, sqlite3 (standard library)
"""

import sqlite3
from datetime import date
from pathlib import Path

from src.domain.entities.broker_flow import BrokerDailyFlow
from src.domain.ports.broker_data_repository import BrokerDataRepositoryError
from src.infrastructure.persistence.sqlite_broker_row_mappers import row_to_broker_daily_flow
from src.infrastructure.persistence.sqlite_broker_schema import connect_sqlite_broker_db


class SQLiteBrokerDailyFlowStore:
    """Persistence for broker_daily_flow only."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        return connect_sqlite_broker_db(self._db_path)

    def save_broker_daily_flows(self, flows: list[BrokerDailyFlow]) -> None:
        """Upsert real per-day per-broker flow records into broker_daily_flow."""
        if not flows:
            return
        try:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO broker_daily_flow
                        (ticker, date, broker_code, broker_name, source,
                         buy_lot, sell_lot, net_lot,
                         buy_value, sell_value, net_value,
                         avg_buy_price, avg_sell_price, avg_price,
                         buy_pct, sell_pct)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, date, broker_code, source) DO UPDATE SET
                        broker_name    = excluded.broker_name,
                        buy_lot        = excluded.buy_lot,
                        sell_lot       = excluded.sell_lot,
                        net_lot        = excluded.net_lot,
                        buy_value      = excluded.buy_value,
                        sell_value     = excluded.sell_value,
                        net_value      = excluded.net_value,
                        avg_buy_price  = excluded.avg_buy_price,
                        avg_sell_price = excluded.avg_sell_price,
                        avg_price      = excluded.avg_price,
                        buy_pct        = excluded.buy_pct,
                        sell_pct       = excluded.sell_pct
                    """,
                    [
                        (
                            f.ticker.upper(),
                            f.date.isoformat(),
                            f.broker_code.upper(),
                            f.broker_name,
                            f.source,
                            f.buy_lot,
                            f.sell_lot,
                            f.net_lot,
                            str(f.buy_value),
                            str(f.sell_value),
                            str(f.net_value),
                            str(f.avg_buy_price),
                            str(f.avg_sell_price),
                            str(f.avg_price),
                            f.buy_pct,
                            f.sell_pct,
                        )
                        for f in flows
                    ],
                )
                conn.commit()
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to save broker daily flows: {e}") from e

    def get_broker_daily_flows(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        broker_codes: list[str] | None = None,
        source: str | None = None,
    ) -> list[BrokerDailyFlow]:
        """Retrieve per-broker daily flow records sorted by (date, broker_code).

        Note on Imbalance: Summing net flows across all returned records for a
        particular date will result in a non-zero imbalance. This is expected
        because the repository only tracks select high-volume/institutional
        desks rather than the entire broker universe.
        """
        try:
            with self._get_connection() as conn:
                query = "SELECT * FROM broker_daily_flow WHERE ticker = ?"
                params: list = [ticker.upper()]
                if start_date:
                    query += " AND date >= ?"
                    params.append(start_date.isoformat())
                if end_date:
                    query += " AND date <= ?"
                    params.append(end_date.isoformat())
                if broker_codes:
                    placeholders = ",".join("?" * len(broker_codes))
                    query += f" AND broker_code IN ({placeholders})"
                    params.extend(c.upper() for c in broker_codes)
                if source:
                    query += " AND source = ?"
                    params.append(source)
                query += " ORDER BY date ASC, broker_code ASC"
                rows = conn.execute(query, params).fetchall()
            return [row_to_broker_daily_flow(r) for r in rows]
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get broker daily flows: {e}") from e

    def get_broker_daily_flow_date_range(
        self,
        ticker: str,
        source: str | None = None,
    ) -> tuple[date, date] | None:
        """Get earliest and latest date in broker_daily_flow for a ticker."""
        try:
            with self._get_connection() as conn:
                params: list = [ticker.upper()]
                where = "WHERE ticker = ?"
                if source:
                    where += " AND source = ?"
                    params.append(source)
                row = conn.execute(
                    f"SELECT MIN(date) AS min_date, MAX(date) AS max_date "
                    f"FROM broker_daily_flow {where}",
                    params,
                ).fetchone()
            if not row or not row["min_date"]:
                return None
            return (
                date.fromisoformat(row["min_date"]),
                date.fromisoformat(row["max_date"]),
            )
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(
                f"Failed to get broker daily flow date range: {e}"
            ) from e

    def get_broker_daily_flows_by_code(
        self,
        broker_code: str,
        start_date: date | None = None,
        end_date: date | None = None,
        ticker: str | None = None,
        source: str | None = None,
    ) -> list[BrokerDailyFlow]:
        """Retrieve rows for one broker_code across tickers (desk-centric)."""
        try:
            with self._get_connection() as conn:
                query = "SELECT * FROM broker_daily_flow WHERE broker_code = ?"
                params: list = [broker_code.upper()]
                if start_date:
                    query += " AND date >= ?"
                    params.append(start_date.isoformat())
                if end_date:
                    query += " AND date <= ?"
                    params.append(end_date.isoformat())
                if ticker:
                    query += " AND ticker = ?"
                    params.append(ticker.upper())
                if source:
                    query += " AND source = ?"
                    params.append(source)
                query += " ORDER BY date ASC, ticker ASC"
                rows = conn.execute(query, params).fetchall()
            return [row_to_broker_daily_flow(r) for r in rows]
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(
                f"Failed to get broker daily flows by code: {e}"
            ) from e
