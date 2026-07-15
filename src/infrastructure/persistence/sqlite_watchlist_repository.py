"""
SQLiteWatchlistRepository — persist and retrieve named screener snapshots.

Schema: screen_snapshots table, one row per ticker per snapshot run.
Multiple snapshots with the same name form a time-series (latest = most recent saved_at).

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


class SQLiteWatchlistRepository:
    """Persist named screener snapshots and retrieve them for comparison.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str | Path = Path("data.db")) -> None:
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS screen_snapshots (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    name              TEXT    NOT NULL,
                    saved_at          TEXT    NOT NULL,
                    universe          TEXT    NOT NULL DEFAULT '',
                    window_days       INTEGER NOT NULL DEFAULT 7,
                    ticker            TEXT    NOT NULL,
                    rank              INTEGER NOT NULL,
                    flow_score        REAL    NOT NULL,
                    composite_score   REAL,
                    consecutive_streak INTEGER NOT NULL DEFAULT 0,
                    net_buy_ratio     REAL    NOT NULL DEFAULT 0,
                    bci_label         TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_name_saved
                ON screen_snapshots(name, saved_at DESC)
            """)

    # ── Write ────────────────────────────────────────────────────────────────

    def save_snapshot(self, entries: list[ScreenSnapshotEntry]) -> None:
        """Persist all entries for one snapshot run (same name + saved_at)."""
        if not entries:
            return
        with self._get_conn() as conn:
            conn.executemany(
                """
                INSERT INTO screen_snapshots
                    (name, saved_at, universe, window_days, ticker, rank,
                     flow_score, composite_score, consecutive_streak, net_buy_ratio, bci_label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        e.name,
                        e.saved_at.isoformat(),
                        e.universe,
                        e.window_days,
                        e.ticker,
                        e.rank,
                        e.flow_score,
                        e.composite_score,
                        e.consecutive_streak,
                        e.net_buy_ratio,
                        e.bci_label,
                    )
                    for e in entries
                ],
            )

    # ── Read ─────────────────────────────────────────────────────────────────

    def get_latest_snapshot(self, name: str) -> list[ScreenSnapshotEntry]:
        """Return the most recently saved entries for the given name."""
        with self._get_conn() as conn:
            saved_at = conn.execute(
                "SELECT MAX(saved_at) FROM screen_snapshots WHERE name=?", (name,)
            ).fetchone()[0]
            if not saved_at:
                return []
            rows = conn.execute(
                """
                SELECT * FROM screen_snapshots
                WHERE name=? AND saved_at=?
                ORDER BY rank ASC
                """,
                (name, saved_at),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def list_snapshots(self) -> list[dict]:
        """Return summary info for all snapshot names: name, count, latest saved_at."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                WITH latest AS (
                    SELECT name, MAX(saved_at) AS latest_saved_at
                    FROM screen_snapshots
                    GROUP BY name
                ),
                latest_rows AS (
                    SELECT s.*
                    FROM screen_snapshots s
                    JOIN latest l
                      ON l.name = s.name
                     AND l.latest_saved_at = s.saved_at
                )
                SELECT
                    name,
                    COUNT(*) AS ticker_count,
                    saved_at AS latest_saved_at,
                    MIN(universe) AS universe,
                    MIN(window_days) AS window_days
                FROM latest_rows
                GROUP BY name, saved_at
                ORDER BY latest_saved_at DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def snapshot_exists(self, name: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM screen_snapshots WHERE name=? LIMIT 1", (name,)
            ).fetchone()
        return row is not None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _row_to_entry(self, row: sqlite3.Row) -> ScreenSnapshotEntry:
        return ScreenSnapshotEntry(
            name=row["name"],
            saved_at=datetime.fromisoformat(row["saved_at"]),
            universe=row["universe"] or "",
            window_days=row["window_days"],
            ticker=row["ticker"],
            rank=row["rank"],
            flow_score=row["flow_score"],
            composite_score=row["composite_score"],
            consecutive_streak=row["consecutive_streak"],
            net_buy_ratio=row["net_buy_ratio"],
            bci_label=row["bci_label"],
        )
