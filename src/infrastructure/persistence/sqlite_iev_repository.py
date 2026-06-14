"""
SQLite repository for IEV/IEP snapshots.

Stores the ranked list of IEV movers and their IEP (Indicative Equilibrium Price)
captured during the IDX pre-open auction window (08:45–09:00 WIB) each trading day.

Two daily captures:
  08:50 WIB — IEV rankings (early mover signal)
  08:55 WIB — IEP refresh (more settled price, 5 min before auction close)
Both upsert into the same row; the later run's IEP overwrites the earlier one.

Layer: Infrastructure
"""

import sqlite3
from datetime import date
from dataclasses import dataclass
from pathlib import Path

from src.domain.value_objects.screener_result import MoverData


@dataclass(frozen=True)
class IEVSnapshot:
    """One ticker's IEV/IEP entry for a given trading date."""

    date: date
    ticker: str
    iev: int
    rank: int               # 1 = highest IEV mover that day
    iep: int | None = None  # Indicative Equilibrium Price in IDR (None if not captured)


class SQLiteIEVRepository:
    """Persist and query IEV/IEP snapshots in the local SQLite database."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS iev_snapshots (
                    date       TEXT NOT NULL,
                    ticker     TEXT NOT NULL,
                    iev        INTEGER NOT NULL,
                    rank       INTEGER NOT NULL,
                    iep        INTEGER,
                    fetched_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (date, ticker)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_iev_snapshots_date
                ON iev_snapshots (date)
            """)
            # Migration: add iep column to existing tables that lack it
            try:
                conn.execute("ALTER TABLE iev_snapshots ADD COLUMN iep INTEGER")
            except Exception:
                pass  # column already exists

    def save_snapshot(self, snapshot_date: date, movers: list[MoverData]) -> int:
        """Upsert IEV+IEP movers for a date.

        Args:
            snapshot_date: The trading date.
            movers: List of MoverData sorted by IEV descending. rank is derived from position.

        Returns:
            Number of rows written.
        """
        rows = [
            (snapshot_date.isoformat(), m.ticker.upper(), m.iev, rank + 1, m.iep)
            for rank, m in enumerate(movers)
        ]
        with self._get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO iev_snapshots (date, ticker, iev, rank, iep)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(date, ticker) DO UPDATE SET
                    iev        = excluded.iev,
                    rank       = excluded.rank,
                    iep        = excluded.iep,
                    fetched_at = datetime('now')
                """,
                rows,
            )
        return len(rows)

    def get_snapshot(self, snapshot_date: date, top_n: int | None = None) -> list[IEVSnapshot]:
        """Return IEV/IEP movers for a date, ordered by rank ascending (rank 1 = best).

        Args:
            snapshot_date: The trading date.
            top_n: If set, return only the top-N ranked movers.
        """
        sql = "SELECT date, ticker, iev, rank, iep FROM iev_snapshots WHERE date = ? ORDER BY rank ASC"
        params: tuple = (snapshot_date.isoformat(),)
        if top_n is not None:
            sql += " LIMIT ?"
            params = (snapshot_date.isoformat(), top_n)
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            IEVSnapshot(
                date=date.fromisoformat(r["date"]),
                ticker=r["ticker"],
                iev=r["iev"],
                rank=r["rank"],
                iep=r["iep"],
            )
            for r in rows
        ]

    def has_snapshot(self, snapshot_date: date) -> bool:
        """Return True if at least one row exists for this date."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM iev_snapshots WHERE date = ? LIMIT 1",
                (snapshot_date.isoformat(),),
            ).fetchone()
        return row is not None

    def get_snapshot_dates(self) -> list[date]:
        """Return all dates that have snapshot data, ascending."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT date FROM iev_snapshots ORDER BY date ASC"
            ).fetchall()
        return [date.fromisoformat(r["date"]) for r in rows]

    def get_coverage(self) -> dict:
        """Return summary: total dates, first/last date, avg movers per day, IEP fill rate."""
        with self._get_connection() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(DISTINCT date)                                          AS total_dates,
                    MIN(date)                                                     AS first_date,
                    MAX(date)                                                     AS last_date,
                    COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT date), 0)            AS avg_movers_per_day,
                    SUM(CASE WHEN iep IS NOT NULL THEN 1 ELSE 0 END) * 1.0
                        / NULLIF(COUNT(*), 0) * 100                              AS iep_fill_pct
                FROM iev_snapshots
            """).fetchone()
        if not row or not row["total_dates"]:
            return {
                "total_dates": 0, "first_date": None, "last_date": None,
                "avg_movers_per_day": 0, "iep_fill_pct": 0.0,
            }
        return {
            "total_dates": row["total_dates"],
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "avg_movers_per_day": round(row["avg_movers_per_day"], 1),
            "iep_fill_pct": round(row["iep_fill_pct"] or 0.0, 1),
        }
