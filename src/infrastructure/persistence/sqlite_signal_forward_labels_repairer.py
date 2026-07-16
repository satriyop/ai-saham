"""
SQLite implementation of SignalForwardLabelsRepairer for DQ-001L.

Manages the signal_forward_labels_quarantine table and performs
transactional quarantine+delete of orphan signal_forward_labels rows
(rows whose (ticker, signal_date, observation_captured_at) have no
matching candidate_observations row).

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SOURCE_COLUMNS: tuple[str, ...] = (
    "id",
    "ticker",
    "signal_date",
    "horizon",
    "observation_captured_at",
    "entry_reference_price",
    "label_window_start",
    "label_window_end",
    "close_return",
    "max_forward_return",
    "max_adverse_excursion",
    "days_to_peak",
    "days_to_trough",
    "stop_would_trigger",
    "target_would_trigger",
    "outcome_label",
    "unavailable_reason",
    "fingerprint_json",
    "schema_version",
    "created_at",
    "updated_at",
    "decision_at",
    "latest_completed_session",
    "analysis_as_of",
    "market_session_name",
    "is_eod_pending",
    "resolution_source",
    "resolution_notes_json",
)

_QUARANTINE_TABLE = "signal_forward_labels_quarantine"

_CREATE_QUARANTINE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {_QUARANTINE_TABLE} (
    quarantine_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_row_id                INTEGER NOT NULL,
    id                          INTEGER,
    ticker                      TEXT,
    signal_date                 TEXT,
    horizon                     TEXT,
    observation_captured_at     TEXT,
    entry_reference_price       TEXT,
    label_window_start          TEXT,
    label_window_end            TEXT,
    close_return                REAL,
    max_forward_return          REAL,
    max_adverse_excursion       REAL,
    days_to_peak                INTEGER,
    days_to_trough              INTEGER,
    stop_would_trigger          INTEGER,
    target_would_trigger        INTEGER,
    outcome_label               TEXT,
    unavailable_reason          TEXT,
    fingerprint_json            TEXT,
    schema_version              INTEGER,
    created_at                  TEXT,
    updated_at                  TEXT,
    decision_at                 TEXT,
    latest_completed_session    TEXT,
    analysis_as_of              TEXT,
    market_session_name         TEXT,
    is_eod_pending               INTEGER,
    resolution_source           TEXT,
    resolution_notes_json       TEXT,
    quarantine_reason           TEXT NOT NULL,
    quarantined_at              TEXT NOT NULL,
    repair_run_id                TEXT NOT NULL,
    original_table               TEXT NOT NULL DEFAULT 'signal_forward_labels',
    quarantine_schema_version    INTEGER NOT NULL DEFAULT 1,
    UNIQUE(source_row_id)
)
"""

_ORPHAN_REASON = "ORPHAN_CANDIDATE_OBSERVATION"
_JOIN_COLUMNS = ("ticker", "signal_date", "observation_captured_at")


class SQLiteSignalForwardLabelsRepairer:
    """SQLite repairer that quarantines orphan signal_forward_labels rows."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_quarantine_table(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_QUARANTINE_TABLE)
            conn.commit()

    def quarantine_and_delete_orphans(self, repair_run_id: str) -> tuple[int, int]:
        """Transactionally quarantine+delete orphan signal_forward_labels rows.

        Orphans = rows whose (ticker, signal_date, observation_captured_at)
        have no matching (ticker, snapshot_date, captured_at) in
        candidate_observations.  Uses SQLite rowid as the stable repair
        identity.  Returns (quarantined_row_count, deleted_row_count).
        Rolls back and raises if the deleted count does not match the
        quarantined count.
        """
        quarantined_at = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            existing_columns = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM pragma_table_info('signal_forward_labels')"
                )
            }
            select_columns = [c for c in SOURCE_COLUMNS if c in existing_columns]
            co_ticker_alias = "co_ticker"
            co_snapshot_date_alias = "co_snapshot_date"
            co_captured_at_alias = "co_captured_at"

            conn.execute("BEGIN")
            orphan_rows = conn.execute(
                f"SELECT l.rowid AS _source_rowid, "
                f"{', '.join(f'l.{c}' for c in select_columns)} "
                f"FROM signal_forward_labels l "
                f"LEFT JOIN candidate_observations o "
                f"ON o.ticker = l.ticker "
                f"AND o.snapshot_date = l.signal_date "
                f"AND o.captured_at = l.observation_captured_at "
                f"WHERE o.ticker IS NULL"
            ).fetchall()

            quarantined_count = 0
            deleted_count = 0
            for row in orphan_rows:
                source_rowid = row["_source_rowid"]
                values = [row[col] for col in select_columns]
                placeholders = ", ".join("?" for _ in select_columns)
                cursor = conn.execute(
                    f"INSERT OR IGNORE INTO {_QUARANTINE_TABLE} "
                    f"(source_row_id, {', '.join(select_columns)}, quarantine_reason, "
                    f"quarantined_at, repair_run_id, original_table, "
                    f"quarantine_schema_version) "
                    f"VALUES (?, {placeholders}, ?, ?, ?, ?, ?)",
                    (
                        source_rowid,
                        *values,
                        _ORPHAN_REASON,
                        quarantined_at,
                        repair_run_id,
                        "signal_forward_labels",
                        1,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Expected to insert 1 quarantine row for source "
                        f"rowid={source_rowid} but inserted {cursor.rowcount}. "
                        f"Rolling back."
                    )
                quarantined_count += 1

                delete_cursor = conn.execute(
                    "DELETE FROM signal_forward_labels WHERE rowid = ?",
                    (source_rowid,),
                )
                if delete_cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Expected to delete 1 row for source rowid={source_rowid} "
                        f"but deleted {delete_cursor.rowcount}. Rolling back."
                    )
                deleted_count += 1

            if deleted_count != quarantined_count:
                raise RuntimeError(
                    f"Deleted row count ({deleted_count}) does not match "
                    f"quarantined row count ({quarantined_count}). Rolling back."
                )

            conn.commit()
            return quarantined_count, deleted_count
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
