"""
SQLite repository for IEV/IEP snapshots.

Stores the ranked list of IEV movers and their IEP (Indicative Equilibrium Price)
captured during the IDX pre-open auction window (08:45–09:00 WIB) each trading day.

Locked-input NCP window:
  08:56–08:57:59 WIB: existing orders cannot be amended or withdrawn, while
  new orders may still enter. Snapshots inside [08:56, 08:58) carry
  is_ncp_locked=1. Pre-opening matching begins at 08:58 and is kept separate.

Typical decision workflow:
  08:45–08:55 WIB — discovery snapshots (pre-NCP, diagnostic)
  08:56 WIB       — locked IEV baseline
  08:57 WIB       — final live decision snapshot (owned by pre-open capture)

Every run appends a row to iev_snapshot_history. The canonical iev_snapshots
table keeps one row per (date, ticker) — always the latest — for backward
compatibility. The NCP flag on the canonical row is sticky: once set to 1 it
cannot be downgraded by a later pre-NCP run.

Layer: Infrastructure
"""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from src.domain.value_objects.idx_market import (
    IDX_TIMEZONE,
    NCP_LOCK_TIME,
    PRE_OPEN_MATCHING_START,
)
from src.domain.value_objects.screener_result import MoverData


@dataclass(frozen=True)
class IEVSnapshot:
    """One ticker's IEV/IEP entry for a given trading date."""

    date: date
    ticker: str
    iev: int
    rank: int  # 1 = highest IEV mover that day
    iep: int | None = None  # Indicative Equilibrium Price in IDR (None if not captured)
    is_ncp_locked: int = 0


class SQLiteIEVRepository:
    """Persist and query IEV/IEP snapshots in the local SQLite database."""

    def __init__(self, db_path: str | Path, *, initialize_schema: bool = True) -> None:
        self._db_path = Path(db_path).expanduser()
        if initialize_schema:
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
        collection_started_at: datetime | None = None,
    ) -> int:
        """Upsert IEV+IEP movers for a date and append to history.

        Args:
            snapshot_date: The trading date.
            movers: List of MoverData sorted by IEV descending. rank is derived from position.
            collected_at: Wall-clock completion time (naive local). Defaults to now().
            collection_started_at: Optional wall-clock start time. When supplied,
                the complete interval must stay inside [08:56, 08:58) to set
                is_ncp_locked. Defaults to collected_at for point snapshots.

        Returns:
            Number of canonical rows written.
        """
        if not movers:
            return 0

        ts = collected_at or datetime.now()
        started_at = collection_started_at or ts
        is_ncp_locked = (
            1
            if (
                started_at.date() == snapshot_date
                and ts.date() == snapshot_date
                and NCP_LOCK_TIME <= started_at.time()
                and started_at <= ts
                and ts.time() < PRE_OPEN_MATCHING_START
            )
            else 0
        )
        ts_str = ts.isoformat(timespec="seconds")

        rows = [
            (
                snapshot_date.isoformat(),
                m.ticker.upper(),
                m.iev,
                rank + 1,
                m.iep,
                ts_str,
                is_ncp_locked,
            )
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
        sql = (
            "SELECT date, ticker, iev, rank, iep, is_ncp_locked "
            "FROM iev_snapshots WHERE date = ? ORDER BY rank ASC"
        )
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
                is_ncp_locked=r["is_ncp_locked"],
            )
            for r in rows
        ]

    def get_ncp_snapshot(
        self,
        snapshot_date: date,
        top_n: int | None = None,
    ) -> list[IEVSnapshot]:
        """Return the latest locked-input history batch for snapshot_date.

        Strategy:
          1. Find the latest [08:56, 08:58) locked-input batch for this date.
          2. Return all rows from that batch ordered by rank ASC.
          3. If no locked-input history exists, fall back to get_snapshot()
             (handles data collected before NCP tracking was added).

        Args:
            snapshot_date: The trading date.
            top_n: If set, return only the top-N movers.
        """
        date_str = snapshot_date.isoformat()
        window_start = datetime.combine(snapshot_date, NCP_LOCK_TIME).isoformat(timespec="seconds")
        matching_start = datetime.combine(snapshot_date, PRE_OPEN_MATCHING_START).isoformat(
            timespec="seconds"
        )
        sql = """
            SELECT date, ticker, iev, rank, iep, is_ncp_locked
            FROM iev_snapshot_history
            WHERE date = ?
              AND is_ncp_locked = 1
              AND collected_at >= ?
              AND collected_at < ?
              AND collected_at = (
                  SELECT MAX(collected_at)
                  FROM iev_snapshot_history
                  WHERE date = ?
                    AND is_ncp_locked = 1
                    AND collected_at >= ?
                    AND collected_at < ?
              )
            ORDER BY rank ASC
        """
        params: tuple = (
            date_str,
            window_start,
            matching_start,
            date_str,
            window_start,
            matching_start,
        )
        if top_n is not None:
            sql += " LIMIT ?"
            params = (*params, top_n)

        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()

        if not rows:
            return self.get_snapshot(snapshot_date, top_n)

        # Rows are filtered to is_ncp_locked=1; still map the column so callers
        # (pre-open board / agent NCP labels) do not see the dataclass default 0.
        return [
            IEVSnapshot(
                date=date.fromisoformat(r["date"]),
                ticker=r["ticker"],
                iev=r["iev"],
                rank=r["rank"],
                iep=r["iep"],
                is_ncp_locked=r["is_ncp_locked"],
            )
            for r in rows
        ]

    def ncp_baseline_iev(self, snapshot_date: date) -> dict[str, int]:
        """Return {ticker: baseline_iev} from the latest 08:56 NCP-locked batch.

        Read projection over get_ncp_snapshot for the IEVBaselineReadPort — lets the
        daily briefing compute delta_iev without leaking the IEVSnapshot type across
        the application boundary. Empty when no locked baseline exists.
        """
        return {snap.ticker: snap.iev for snap in self.get_ncp_snapshot(snapshot_date)}

    def get_iev_delta(self, snapshot_date: date) -> dict[str, int]:
        """Return diagnostic all-session ΔIEV per ticker for snapshot_date.

        ΔIEV = last_history_iev - first_history_iev (chronological order).
        Tickers with only one history row are omitted — no delta is meaningful.
        This method is not production signal evidence because it can mix
        pre-NCP, locked-input, and matching-period snapshots.

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

    def get_locked_iev_baseline(
        self,
        snapshot_date: date,
        *,
        before: datetime,
    ) -> dict[str, int]:
        """Return each ticker's earliest locked-input IEV before live collection.

        Only rows inside [08:56, 08:58) on ``snapshot_date`` are eligible.
        ``before`` is the authoritative workflow's collection start, so the
        returned baseline is strictly earlier than the final live mover fetch.
        Missing tickers remain absent; callers must not substitute pre-NCP rows.
        """
        if before.tzinfo is None:
            raise ValueError("locked IEV baseline cutoff must be timezone-aware")
        local_before = before.astimezone(IDX_TIMEZONE)
        if local_before.date() != snapshot_date:
            raise ValueError("locked IEV baseline cutoff must match snapshot_date")

        window_start = datetime.combine(snapshot_date, NCP_LOCK_TIME)
        matching_start = datetime.combine(snapshot_date, PRE_OPEN_MATCHING_START)
        cutoff = min(local_before.replace(tzinfo=None), matching_start)
        if cutoff <= window_start:
            return {}

        sql = """
            WITH ranked AS (
                SELECT
                    ticker,
                    iev,
                    ROW_NUMBER() OVER (
                        PARTITION BY ticker
                        ORDER BY collected_at ASC, id ASC
                    ) AS rn
                FROM iev_snapshot_history
                WHERE date = ?
                  AND is_ncp_locked = 1
                  AND collected_at >= ?
                  AND collected_at < ?
            )
            SELECT ticker, iev
            FROM ranked
            WHERE rn = 1
        """
        with self._get_connection() as conn:
            rows = conn.execute(
                sql,
                (
                    snapshot_date.isoformat(),
                    window_start.isoformat(timespec="seconds"),
                    cutoff.isoformat(timespec="seconds"),
                ),
            ).fetchall()
        return {r["ticker"]: r["iev"] for r in rows}

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
                    COUNT(*) * 1.0
                        / NULLIF(COUNT(DISTINCT date), 0) AS avg_movers_per_day,
                    SUM(CASE WHEN iep IS NOT NULL THEN 1 ELSE 0 END) * 1.0
                        / NULLIF(COUNT(*), 0) * 100                              AS iep_fill_pct
                FROM iev_snapshots
            """).fetchone()
        if not row or not row["total_dates"]:
            return {
                "total_dates": 0,
                "first_date": None,
                "last_date": None,
                "avg_movers_per_day": 0,
                "iep_fill_pct": 0.0,
            }
        return {
            "total_dates": row["total_dates"],
            "first_date": row["first_date"],
            "last_date": row["last_date"],
            "avg_movers_per_day": round(row["avg_movers_per_day"], 1),
            "iep_fill_pct": round(row["iep_fill_pct"] or 0.0, 1),
        }

    def get_ncp_lock_window_coverage(self, *, recent_days: int = 30) -> dict:
        """Per-day NCP lock-window batch metrics from ``iev_snapshot_history``.

        Success metric is **did this calendar day write any is_ncp_locked=1
        rows**, not the global NCP fraction of all history rows. Discovery-only
        days (pre-08:56 fetches) correctly report ncp_tickers=0. Typical
        successful days show ``ncp_tickers`` near the fetch ``--top-n`` (default
        50) — that is a population limit, not full-board coverage.
        """
        if recent_days < 1:
            raise ValueError("recent_days must be >= 1")
        with self._get_connection() as conn:
            day_rows = conn.execute(
                """
                SELECT
                    date,
                    COUNT(*) AS history_rows,
                    SUM(CASE WHEN is_ncp_locked = 1 THEN 1 ELSE 0 END) AS ncp_rows,
                    COUNT(DISTINCT CASE WHEN is_ncp_locked = 1 THEN ticker END)
                        AS ncp_tickers
                FROM iev_snapshot_history
                GROUP BY date
                ORDER BY date DESC
                LIMIT ?
                """,
                (recent_days,),
            ).fetchall()
            totals = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT date) AS history_dates,
                    COUNT(DISTINCT CASE WHEN is_ncp_locked = 1 THEN date END)
                        AS ncp_dates,
                    COUNT(*) AS history_rows,
                    SUM(CASE WHEN is_ncp_locked = 1 THEN 1 ELSE 0 END) AS ncp_rows
                FROM iev_snapshot_history
                """
            ).fetchone()

        days = [
            {
                "date": r["date"],
                "history_rows": int(r["history_rows"] or 0),
                "ncp_rows": int(r["ncp_rows"] or 0),
                "ncp_tickers": int(r["ncp_tickers"] or 0),
                "has_lock_batch": int(r["ncp_tickers"] or 0) > 0,
            }
            for r in day_rows
        ]
        lock_days = sum(1 for d in days if d["has_lock_batch"])
        return {
            "history_dates": int(totals["history_dates"] or 0) if totals else 0,
            "ncp_dates": int(totals["ncp_dates"] or 0) if totals else 0,
            "history_rows": int(totals["history_rows"] or 0) if totals else 0,
            "ncp_rows": int(totals["ncp_rows"] or 0) if totals else 0,
            "recent_days_reported": len(days),
            "recent_lock_batch_days": lock_days,
            "recent_lock_batch_rate": (round(lock_days / len(days), 4) if days else 0.0),
            "days": days,
            "notes": (
                "ncp_tickers is the lock-window population size (usually ~fetch --top-n)",
                "has_lock_batch=false means no NCP-locked history that day "
                "(ops gap or pre-NCP only)",
            ),
        }

    def get_ticker_history(self, ticker: str, limit: int = 5) -> list[IEVSnapshot]:
        """Return the latest snapshots for a specific ticker.

        Args:
            ticker: Stock ticker symbol.
            limit: Maximum number of rows to return.
        """
        sql = """
            SELECT date, ticker, iev, rank, iep, is_ncp_locked
            FROM iev_snapshots
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT ?
        """
        with self._get_connection() as conn:
            rows = conn.execute(sql, (ticker.upper(), limit)).fetchall()
        return [
            IEVSnapshot(
                date=date.fromisoformat(r["date"]),
                ticker=r["ticker"],
                iev=r["iev"],
                rank=r["rank"],
                iep=r["iep"],
                is_ncp_locked=r["is_ncp_locked"],
            )
            for r in rows
        ]
