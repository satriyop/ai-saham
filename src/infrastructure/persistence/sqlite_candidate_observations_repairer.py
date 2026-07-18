"""
SQLite implementation of CandidateObservationsRepairer for DQ-001J.

Manages the candidate_observations_quarantine table and performs
transactional quarantine+delete of legacy candidate_observations rows
(config_hash IS NULL or empty after trim; all rows if config_hash column is
missing).

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)

# Full set of candidate_observations columns copied into quarantine, in the
# order the original table's schema introduced them. Columns absent from an
# older DB are stored as NULL in quarantine (see SQLiteCandidateObservationsRepairReader).
#
# NOTE: "id" here is plain copied data, not the repair identity — an even
# older DB could in principle lack an "id" column entirely. Every SQLite
# table (that isn't WITHOUT ROWID) always has a rowid, so `rowid` is used as
# the stable repair/delete identity instead (see _source_rowid below).
SOURCE_COLUMNS: tuple[str, ...] = (
    "id",
    "ticker",
    "snapshot_date",
    "captured_at",
    "schema_version",
    "payload_json",
    "workflow",
    "window_sessions",
    "data_as_of_date",
    "config_hash",
    "decision_at",
    "latest_completed_session",
    "analysis_as_of",
    "market_session_name",
    "is_eod_pending",
    "resolution_source",
    "resolution_notes_json",
)

_QUARANTINE_TABLE = "candidate_observations_quarantine"

_CREATE_QUARANTINE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {_QUARANTINE_TABLE} (
    quarantine_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    source_row_id                INTEGER NOT NULL,
    id                          INTEGER,
    ticker                      TEXT,
    snapshot_date               TEXT,
    captured_at                 TEXT,
    schema_version              INTEGER,
    payload_json                TEXT,
    workflow                    TEXT,
    window_sessions             INTEGER,
    data_as_of_date             TEXT,
    config_hash                 TEXT,
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
    original_table               TEXT NOT NULL DEFAULT 'candidate_observations',
    quarantine_schema_version    INTEGER NOT NULL DEFAULT 1,
    UNIQUE(source_row_id)
)
"""

_LEGACY_WHERE = (
    "config_hash IS NULL OR TRIM(config_hash) = '' "
    f"OR schema_version != {CANDIDATE_OBSERVATION_SCHEMA_VERSION}"
)
_LEGACY_REASON = "LEGACY_MISSING_CONFIG_HASH_OR_OLD_SCHEMA"


class SQLiteCandidateObservationsRepairer:
    """SQLite repairer that quarantines legacy candidate_observations rows."""

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

    def quarantine_and_delete_legacy(self, repair_run_id: str) -> tuple[int, int]:
        """Transactionally quarantine+delete legacy candidate_observations rows.

        Rows are identified for delete by SQLite `rowid`, not the optional
        `id` column, so this works even against a schema that predates the
        `id` column. Returns (quarantined_row_count, deleted_row_count).
        Rolls back and raises if the deleted count does not match the
        quarantined count.
        """
        quarantined_at = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            existing_columns = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM pragma_table_info('candidate_observations')"
                )
            }
            config_hash_missing = "config_hash" not in existing_columns

            select_columns = [c for c in SOURCE_COLUMNS if c in existing_columns]
            where_clause = "1=1" if config_hash_missing else _LEGACY_WHERE

            conn.execute("BEGIN")
            legacy_rows = conn.execute(
                f"SELECT rowid AS _source_rowid, {', '.join(select_columns)} "
                f"FROM candidate_observations WHERE {where_clause}"
            ).fetchall()

            quarantined_count = 0
            deleted_count = 0
            for row in legacy_rows:
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
                        _LEGACY_REASON,
                        quarantined_at,
                        repair_run_id,
                        "candidate_observations",
                        1,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        f"Expected to insert 1 quarantine row for source rowid="
                        f"{source_rowid} but inserted {cursor.rowcount}. Rolling back."
                    )
                quarantined_count += 1

                delete_cursor = conn.execute(
                    "DELETE FROM candidate_observations WHERE rowid = ?", (source_rowid,)
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
