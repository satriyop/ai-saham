"""
SQLite persistence for foreign_flow_points and foreign_flow_snapshots.

Layer: Infrastructure
Depends on: Domain ports, sqlite3 (standard library)
"""

import sqlite3
from datetime import date
from pathlib import Path

from src.domain.entities.broker_flow import ForeignFlowPoint, ForeignFlowSnapshot
from src.domain.ports.broker_data_repository import BrokerDataRepositoryError
from src.infrastructure.persistence.sqlite_broker_row_mappers import (
    row_to_foreign_flow_point,
    row_to_foreign_flow_snapshot,
)
from src.infrastructure.persistence.sqlite_broker_schema import connect_sqlite_broker_db


class SQLiteForeignFlowStore:
    """Persistence for foreign_flow_points and foreign_flow_snapshots only."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        return connect_sqlite_broker_db(self._db_path)

    def save_foreign_flow_points(self, points: list[ForeignFlowPoint]) -> None:
        if not points:
            return
        try:
            with self._get_connection() as conn:
                conn.executemany(
                    """
                    INSERT INTO foreign_flow_points (
                        ticker, date, source, net_val, net_lot, avg_price
                    )
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
            return [row_to_foreign_flow_point(r) for r in rows]
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
            return [row_to_foreign_flow_snapshot(r) for r in rows]
        except sqlite3.Error as e:
            raise BrokerDataRepositoryError(f"Failed to get foreign flow snapshots: {e}") from e
