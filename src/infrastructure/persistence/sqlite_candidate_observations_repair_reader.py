"""
Read-only SQLite reader for DQ-001J candidate_observations repair.

Opens the database in read-only URI mode (mode=ro) and never executes DDL or
write statements. Returns raw aggregate facts only — no classification or
mutation logic.

Layer: Infrastructure
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from src.application.use_case.repair_candidate_observations_use_case import (
    CandidateObservationsRepairReader,
    RawCandidateObservationsRepairState,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)

_LEGACY_WHERE = (
    "config_hash IS NULL OR TRIM(config_hash) = '' "
    f"OR schema_version != {CANDIDATE_OBSERVATION_SCHEMA_VERSION}"
)


class SQLiteCandidateObservationsRepairReader:
    """Read-only observer of candidate_observations for repair reporting."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def database_exists(self) -> bool:
        return self._db_path.exists()

    def observe_repair_state(self) -> RawCandidateObservationsRepairState:
        if not self._db_path.exists():
            return RawCandidateObservationsRepairState(exists=False)

        with contextlib.closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row

            if not self._table_exists(conn):
                return RawCandidateObservationsRepairState(exists=False)

            missing_columns = self._find_missing_columns(conn)
            config_hash_missing = "config_hash" in missing_columns

            total = self._scalar(conn, "SELECT COUNT(*) FROM candidate_observations")

            if config_hash_missing:
                legacy = total
            else:
                legacy = self._scalar(
                    conn,
                    f"SELECT COUNT(*) FROM candidate_observations WHERE {_LEGACY_WHERE}",
                )
            canonical = total - legacy

            snapshot_date_missing = "snapshot_date" in missing_columns

            snapshot_date_min: str | None = None
            snapshot_date_max: str | None = None
            latest_snapshot_date: str | None = None
            latest_legacy = 0
            latest_canonical = 0

            if snapshot_date_missing:
                # Every row is treated as the "latest" group when there is no
                # snapshot_date to group by.
                if total > 0:
                    latest_legacy = legacy
                    latest_canonical = canonical
            else:
                snapshot_date_min = self._scalar_str(
                    conn, "SELECT MIN(snapshot_date) FROM candidate_observations"
                )
                snapshot_date_max = self._scalar_str(
                    conn, "SELECT MAX(snapshot_date) FROM candidate_observations"
                )

                if total > 0:
                    row = conn.execute(
                        "SELECT snapshot_date, COUNT(*) as total FROM candidate_observations "
                        "GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1"
                    ).fetchone()
                    if row is not None:
                        latest_snapshot_date = row["snapshot_date"]
                        latest_total = row["total"]
                        if config_hash_missing:
                            latest_legacy = latest_total
                            latest_canonical = 0
                        else:
                            canonical_row = conn.execute(
                                "SELECT COUNT(*) as cnt FROM candidate_observations "
                                "WHERE snapshot_date = ? AND NOT (" + _LEGACY_WHERE + ")",
                                (latest_snapshot_date,),
                            ).fetchone()
                            latest_canonical = canonical_row["cnt"] if canonical_row else 0
                            latest_legacy = latest_total - latest_canonical

            return RawCandidateObservationsRepairState(
                exists=True,
                total_row_count=total,
                legacy_row_count=legacy,
                canonical_row_count=canonical,
                snapshot_date_min=snapshot_date_min,
                snapshot_date_max=snapshot_date_max,
                latest_snapshot_date=latest_snapshot_date,
                latest_legacy_row_count=latest_legacy,
                latest_canonical_row_count=latest_canonical,
                missing_columns=missing_columns,
            )

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def _table_exists(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_observations'"
        ).fetchone()
        return row is not None

    def _find_missing_columns(self, conn: sqlite3.Connection) -> tuple[str, ...]:
        from src.infrastructure.persistence.sqlite_candidate_observations_repairer import (
            SOURCE_COLUMNS,
        )

        existing = {
            row["name"]
            for row in conn.execute("SELECT name FROM pragma_table_info('candidate_observations')")
        }
        return tuple(c for c in SOURCE_COLUMNS if c not in existing)

    def _scalar(self, conn: sqlite3.Connection, sql: str) -> int:
        return conn.execute(sql).fetchone()[0] or 0

    def _scalar_str(self, conn: sqlite3.Connection, sql: str) -> str | None:
        row = conn.execute(sql).fetchone()
        return row[0] if row and row[0] else None
