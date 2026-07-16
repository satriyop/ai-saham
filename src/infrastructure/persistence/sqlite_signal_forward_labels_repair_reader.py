"""
Read-only SQLite reader for DQ-001L signal_forward_labels repair.

Opens the database in read-only URI mode (mode=ro) and never executes DDL or
write statements.  Returns raw aggregate facts only — no classification or
mutation logic.

Safe-guarded: if candidate_observations table or required join columns are
missing, the reader returns source_unavailable state — it does NOT fall back
to "all labels are orphans".

Layer: Infrastructure
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from src.application.use_case.repair_signal_forward_labels_use_case import (
    RawSignalForwardLabelsRepairState,
    SignalForwardLabelsRepairReader,
)

_SFL_COLS = ("ticker", "signal_date", "observation_captured_at")
_CO_COLS = ("ticker", "snapshot_date", "captured_at")
_JOIN_COLS = _SFL_COLS + _CO_COLS


class SQLiteSignalForwardLabelsRepairReader:
    """Read-only observer of signal_forward_labels for repair reporting."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def database_exists(self) -> bool:
        return self._db_path.exists()

    def observe_repair_state(self) -> RawSignalForwardLabelsRepairState:
        if not self._db_path.exists():
            return RawSignalForwardLabelsRepairState(exists=False)

        with contextlib.closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row

            if not self._table_exists(conn, "signal_forward_labels"):
                return RawSignalForwardLabelsRepairState(exists=False)

            if not self._table_exists(conn, "candidate_observations"):
                return RawSignalForwardLabelsRepairState(
                    exists=True,
                    source_unavailable=True,
                    source_unavailable_reason="CANDIDATE_OBSERVATIONS_TABLE_MISSING",
                )

            sfl_missing = self._missing_columns(conn, "signal_forward_labels", _SFL_COLS)
            co_missing = self._missing_columns(conn, "candidate_observations", _CO_COLS)
            all_missing = sfl_missing + co_missing

            if all_missing:
                return RawSignalForwardLabelsRepairState(
                    exists=True,
                    source_unavailable=True,
                    source_unavailable_reason="REQUIRED_LINKAGE_COLUMNS_MISSING",
                    missing_columns=all_missing,
                )

            total = self._scalar(conn, "SELECT COUNT(*) FROM signal_forward_labels")

            orphan = self._scalar(
                conn,
                "SELECT COUNT(*) FROM signal_forward_labels l "
                "LEFT JOIN candidate_observations o "
                "ON o.ticker = l.ticker "
                "AND o.snapshot_date = l.signal_date "
                "AND o.captured_at = l.observation_captured_at "
                "WHERE o.ticker IS NULL",
            )
            canonical = total - orphan
            signal_date_min = self._scalar_str(
                conn,
                "SELECT MIN(signal_date) FROM signal_forward_labels",
            )
            signal_date_max = self._scalar_str(
                conn,
                "SELECT MAX(signal_date) FROM signal_forward_labels",
            )

            return RawSignalForwardLabelsRepairState(
                exists=True,
                total_row_count=total,
                orphan_row_count=orphan,
                canonical_row_count=canonical,
                signal_date_min=signal_date_min,
                signal_date_max=signal_date_max,
            )

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def _table_exists(self, conn: sqlite3.Connection, name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None

    def _missing_columns(
        self, conn: sqlite3.Connection, table: str, required: tuple[str, ...]
    ) -> tuple[str, ...]:
        existing = {
            row["name"]
            for row in conn.execute(
                f"SELECT name FROM pragma_table_info('{table}')"
            )
        }
        return tuple(c for c in required if c not in existing)

    def _scalar(self, conn: sqlite3.Connection, sql: str) -> int:
        return conn.execute(sql).fetchone()[0] or 0

    def _scalar_str(self, conn: sqlite3.Connection, sql: str) -> str | None:
        row = conn.execute(sql).fetchone()
        return row[0] if row and row[0] else None
