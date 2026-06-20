"""
SQLite repository for IEV/IEP snapshots.

Stores the ranked list of IEV movers and their IEP (Indicative Equilibrium Price)
captured during the IDX pre-open auction window (08:45–09:00 WIB) each trading day.

NCP (No Cancellation Period) — per Kep-00003/BEI/04-2025, effective 2025-12-15:
  08:56–09:00 WIB: orders in the call auction cannot be amended or withdrawn.
  Snapshots collected inside [08:56, 09:00) carry is_ncp_locked=1 and reflect
  committed demand. Earlier or later snapshots are not NCP-locked.

Two daily captures (typical workflow):
  08:45–08:55 WIB — early IEV mover signal (pre-NCP, is_ncp_locked=0)
  08:56–09:00 WIB — committed IEV/IEP (NCP-locked, is_ncp_locked=1)

Every run appends a row to iev_snapshot_history. The canonical iev_snapshots
table keeps one row per (date, ticker) — always the latest — for backward
compatibility. The NCP flag on the canonical row is sticky: once set to 1 it
cannot be downgraded by a later pre-NCP run.

Layer: Infrastructure
"""

import sqlite3
from datetime import date, datetime, time
from dataclasses import dataclass
from pathlib import Path

from src.domain.value_objects.screener_result import MoverData

# IDX NCP window per Kep-00003/BEI/04-2025 (effective 2025-12-15).
# Snapshots collected inside [08:56, 09:00) are NCP-locked.
NCP_LOCK_TIME: time = time(8, 56)
REGULAR_OPEN_TIME: time = time(9, 0)


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
                    date          TEXT NOT NULL,
                    ticker        TEXT NOT NULL,
                    iev           INTEGER NOT NULL,
                    rank          INTEGER NOT NULL,
                    iep           INTEGER,
                    fetched_at    TEXT DEFAULT (datetime('now')),
                    is_ncp_locked INTEGER NOT NULL DEFAULT 0,
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
            # Migration: add is_ncp_locked to existing tables that lack it
            try:
                conn.execute(
                    "ALTER TABLE iev_snapshots ADD COLUMN is_ncp_locked INTEGER NOT NULL DEFAULT 0"
                )
            except Exception:
                pass  # column already exists

            # Append-only history: every collect-iev run produces a new row here.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS iev_snapshot_history (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    date          TEXT    NOT NULL,
                    ticker        TEXT    NOT NULL,
                    iev           INTEGER NOT NULL,
                    rank          INTEGER NOT NULL,
                    iep           INTEGER,
                    collected_at  TEXT    NOT NULL,
                    is_ncp_locked INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_iev_history_date
                ON iev_snapshot_history (date)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_iev_history_date_ncp
                ON iev_snapshot_history (date, is_ncp_locked)
            """)

    def save_snapshot(
        self,
        snapshot_date: date,
        movers: list[MoverData],
        collected_at: datetime | None = None,
    ) -> int:
        """Upsert IEV+IEP movers for a date and append to history.

        Args:
            snapshot_date: The trading date.
            movers: List of MoverData sorted by IEV descending. rank is derived from position.
            collected_at: Wall-clock time of collection (naive local). Defaults to now().
                          Determines is_ncp_locked (08:56 ≤ time < 09:00 WIB = locked).

        Returns:
            Number of canonical rows written.
        """
        if not movers:
            return 0

        ts = collected_at or datetime.now()
        is_ncp_locked = 1 if NCP_LOCK_TIME <= ts.time() < REGULAR_OPEN_TIME else 0
        ts_str = ts.isoformat(timespec="seconds")

        rows = [
            (snapshot_date.isoformat(), m.ticker.upper(), m.iev, rank + 1, m.iep, ts_str, is_ncp_locked)
            for rank, m in enumerate(movers)
        ]

        with self._get_connection() as conn:
            # Canonical table: one row per (date, ticker); NCP flag is sticky (MAX).
            conn.executemany(
                """
                INSERT INTO iev_snapshots (date, ticker, iev, rank, iep, fetched_at, is_ncp_locked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, ticker) DO UPDATE SET
                    iev           = excluded.iev,
                    rank          = excluded.rank,
                    iep           = excluded.iep,
                    fetched_at    = excluded.fetched_at,
                    is_ncp_locked = MAX(iev_snapshots.is_ncp_locked, excluded.is_ncp_locked)
                """,
                rows,
            )
            # History table: append — every run is a separate row.
            conn.executemany(
                """
                INSERT INTO iev_snapshot_history
                    (date, ticker, iev, rank, iep, collected_at, is_ncp_locked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
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

    def get_ncp_snapshot(
        self,
        snapshot_date: date,
        top_n: int | None = None,
    ) -> list[IEVSnapshot]:
        """Return the latest NCP-locked history batch for snapshot_date.

        Strategy:
          1. Find the latest collected_at where is_ncp_locked=1 for this date.
          2. Return all rows from that batch ordered by rank ASC.
          3. If no NCP-locked history exists, fall back to get_snapshot()
             (handles data collected before NCP tracking was added).

        Args:
            snapshot_date: The trading date.
            top_n: If set, return only the top-N movers.
        """
        date_str = snapshot_date.isoformat()
        sql = """
            SELECT date, ticker, iev, rank, iep
            FROM iev_snapshot_history
            WHERE date = ?
              AND is_ncp_locked = 1
              AND collected_at = (
                  SELECT MAX(collected_at)
                  FROM iev_snapshot_history
                  WHERE date = ? AND is_ncp_locked = 1
              )
            ORDER BY rank ASC
        """
        params: tuple = (date_str, date_str)
        if top_n is not None:
            sql += " LIMIT ?"
            params = (date_str, date_str, top_n)

        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        if not rows:
            return self.get_snapshot(snapshot_date, top_n)

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

    def get_iev_delta(self, snapshot_date: date) -> dict[str, int]:
        """Return ΔIEV per ticker for snapshot_date.

        ΔIEV = last_history_iev - first_history_iev (chronological order).
        Tickers with only one history row are omitted — no delta is meaningful.

        Returns:
            Dict mapping ticker → delta (positive = IEV grew, negative = faded).
        """
        date_str = snapshot_date.isoformat()
        sql = """
            WITH ranked AS (
                SELECT
                    ticker,
                    iev,
                    ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY collected_at ASC)  AS rn_asc,
                    ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY collected_at DESC) AS rn_desc,
                    COUNT(*)    OVER (PARTITION BY ticker)                             AS n
                FROM iev_snapshot_history
                WHERE date = ?
            )
            SELECT
                ticker,
                MAX(CASE WHEN rn_asc  = 1 THEN iev END) AS first_iev,
                MAX(CASE WHEN rn_desc = 1 THEN iev END) AS last_iev
            FROM ranked
            WHERE n >= 2
            GROUP BY ticker
        """
        with self._get_connection() as conn:
            rows = conn.execute(sql, (date_str,)).fetchall()
        return {r["ticker"]: r["last_iev"] - r["first_iev"] for r in rows}

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
