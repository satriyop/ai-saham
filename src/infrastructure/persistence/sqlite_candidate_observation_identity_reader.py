"""
Read-only SQLite reader for DQ-001I candidate_observations identity audit.

Opens the database in read-only URI mode (mode=ro) and never executes DDL or
write statements.  Returns raw aggregate facts only — no classification or
evaluation logic.

Layer: Infrastructure
"""

from __future__ import annotations

import contextlib
import sqlite3
from pathlib import Path

from src.application.use_case.audit_candidate_observation_identity_use_case import (
    CandidateObservationIdentityReader,
    RawCandidateObservationIdentityData,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)

# HIGH-2: the shared schema-version constant is the only source of the
# current canonical version — never hardcode 2 or 3 in these SQL filters.
_CANONICAL_SCHEMA_FILTER = (
    "config_hash IS NOT NULL AND TRIM(config_hash) != '' "
    f"AND schema_version = {CANDIDATE_OBSERVATION_SCHEMA_VERSION}"
)
_LEGACY_SCHEMA_FILTER = (
    "config_hash IS NULL OR TRIM(config_hash) = '' "
    f"OR schema_version != {CANDIDATE_OBSERVATION_SCHEMA_VERSION}"
)

_MISSING_IDENTITY_COLUMNS = (
    "config_hash",
    "workflow",
    "window_sessions",
    "data_as_of_date",
)

_IDENTITY_GROUP_COLUMNS = (
    "ticker",
    "snapshot_date",
    "workflow",
    "window_sessions",
    "data_as_of_date",
    "config_hash",
)


class SQLiteCandidateObservationIdentityReader:
    """Read-only observer of candidate_observations identity.

    Opens SQLite in read-only URI mode.  Never executes DDL or INSERT/UPDATE/DELETE.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path).expanduser()

    def database_exists(self) -> bool:
        return self._db_path.exists()

    def observe_candidate_observation_identity(self) -> RawCandidateObservationIdentityData:
        if not self._db_path.exists():
            return RawCandidateObservationIdentityData(
                exists=False,
                missing_columns=(),
            )

        with contextlib.closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row

            if not self._table_exists(conn):
                return RawCandidateObservationIdentityData(
                    exists=False,
                    missing_columns=(),
                )

            missing_columns = self._find_missing_identity_columns(conn)

            total = self._scalar(conn, "SELECT COUNT(*) FROM candidate_observations")

            if missing_columns:
                config_hash_missing = "config_hash" in missing_columns
                legacy = total if config_hash_missing else self._scalar(
                    conn,
                    "SELECT COUNT(*) FROM candidate_observations "
                    f"WHERE {_LEGACY_SCHEMA_FILTER}",
                )
                canonical = total - legacy
                missing_counts = {}
                for col in _MISSING_IDENTITY_COLUMNS:
                    if col in missing_columns:
                        missing_counts[col] = total
                    elif col == "window_sessions":
                        missing_counts[col] = self._scalar(
                            conn,
                            "SELECT COUNT(*) FROM candidate_observations "
                            "WHERE window_sessions IS NULL OR window_sessions = 0",
                        )
                    else:
                        missing_counts[col] = self._scalar(
                            conn,
                            f"SELECT COUNT(*) FROM candidate_observations "
                            f"WHERE {col} IS NULL OR TRIM({col}) = ''",
                        )

                latest_dep = self._compute_latest_dep_missing_columns(
                    conn, config_hash_missing, total
                )

                legacy_date_sql = (
                    "SELECT snapshot_date, COUNT(*) as row_count "
                    "FROM candidate_observations GROUP BY snapshot_date "
                    "ORDER BY row_count DESC"
                    if config_hash_missing
                    else (
                        "SELECT snapshot_date, COUNT(*) as row_count "
                        "FROM candidate_observations "
                        f"WHERE {_LEGACY_SCHEMA_FILTER} "
                        "GROUP BY snapshot_date ORDER BY row_count DESC"
                    )
                )

                return RawCandidateObservationIdentityData(
                    exists=True,
                    total_row_count=total,
                    canonical_row_count=canonical,
                    legacy_row_count=legacy,
                    snapshot_date_min=self._scalar_str(conn, "SELECT MIN(snapshot_date) FROM candidate_observations"),
                    snapshot_date_max=self._scalar_str(conn, "SELECT MAX(snapshot_date) FROM candidate_observations"),
                    captured_at_min=self._scalar_str(conn, "SELECT MIN(captured_at) FROM candidate_observations"),
                    captured_at_max=self._scalar_str(conn, "SELECT MAX(captured_at) FROM candidate_observations"),
                    missing_identity_counts=missing_counts,
                    workflow_counts=[],
                    window_session_counts=[],
                    legacy_by_snapshot_date=self._rows_as_list(conn, legacy_date_sql),
                    duplicate_identity_group_count=0,
                    duplicate_identity_row_count=0,
                    latest_readiness_dependency=latest_dep,
                    missing_columns=missing_columns,
                )

            legacy = self._scalar(
                conn,
                "SELECT COUNT(*) FROM candidate_observations "
                f"WHERE {_LEGACY_SCHEMA_FILTER}",
            )
            canonical = total - legacy

            missing_counts = {}
            for col in _MISSING_IDENTITY_COLUMNS:
                if col == "window_sessions":
                    missing_counts[col] = self._scalar(
                        conn,
                        "SELECT COUNT(*) FROM candidate_observations "
                        "WHERE window_sessions IS NULL OR window_sessions = 0",
                    )
                else:
                    missing_counts[col] = self._scalar(
                        conn,
                        f"SELECT COUNT(*) FROM candidate_observations "
                        f"WHERE {col} IS NULL OR TRIM({col}) = ''",
                    )

            workflow_counts = self._rows_as_list(
                conn,
                "SELECT COALESCE(NULLIF(TRIM(workflow), ''), '(unknown)') as workflow, "
                "COUNT(*) as row_count FROM candidate_observations "
                "GROUP BY workflow ORDER BY row_count DESC",
            )

            window_session_counts = self._rows_as_list(
                conn,
                "SELECT window_sessions, COUNT(*) as row_count "
                "FROM candidate_observations "
                "GROUP BY window_sessions ORDER BY window_sessions",
            )

            legacy_by_snapshot_date = self._rows_as_list(
                conn,
                "SELECT snapshot_date, COUNT(*) as row_count "
                "FROM candidate_observations "
                f"WHERE {_LEGACY_SCHEMA_FILTER} "
                "GROUP BY snapshot_date ORDER BY row_count DESC",
            )

            duplicate_group_count, duplicate_row_count = self._count_duplicate_identity_groups(conn)

            latest_dep = self._latest_readiness_dependency(conn)

            return RawCandidateObservationIdentityData(
                exists=True,
                total_row_count=total,
                canonical_row_count=canonical,
                legacy_row_count=legacy,
                snapshot_date_min=self._scalar_str(conn, "SELECT MIN(snapshot_date) FROM candidate_observations"),
                snapshot_date_max=self._scalar_str(conn, "SELECT MAX(snapshot_date) FROM candidate_observations"),
                captured_at_min=self._scalar_str(conn, "SELECT MIN(captured_at) FROM candidate_observations"),
                captured_at_max=self._scalar_str(conn, "SELECT MAX(captured_at) FROM candidate_observations"),
                missing_identity_counts=missing_counts,
                workflow_counts=workflow_counts,
                window_session_counts=window_session_counts,
                legacy_by_snapshot_date=legacy_by_snapshot_date,
                duplicate_identity_group_count=duplicate_group_count,
                duplicate_identity_row_count=duplicate_row_count,
                latest_readiness_dependency=latest_dep,
                missing_columns=(),
            )

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self._db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def _table_exists(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='candidate_observations'"
        ).fetchone()
        return row is not None

    def _find_missing_identity_columns(self, conn: sqlite3.Connection) -> tuple[str, ...]:
        existing = {
            row["name"]
            for row in conn.execute("SELECT name FROM pragma_table_info('candidate_observations')")
        }
        return tuple(c for c in _MISSING_IDENTITY_COLUMNS if c not in existing)

    def _scalar(self, conn: sqlite3.Connection, sql: str) -> int:
        return conn.execute(sql).fetchone()[0] or 0

    def _scalar_str(self, conn: sqlite3.Connection, sql: str) -> str | None:
        row = conn.execute(sql).fetchone()
        return row[0] if row and row[0] else None

    def _rows_as_list(self, conn: sqlite3.Connection, sql: str) -> list[dict]:
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def _count_duplicate_identity_groups(
        self, conn: sqlite3.Connection
    ) -> tuple[int, int]:
        groups = conn.execute(
            "SELECT ticker, snapshot_date, workflow, window_sessions, "
            "data_as_of_date, config_hash, COUNT(*) as cnt "
            "FROM candidate_observations "
            f"WHERE {_CANONICAL_SCHEMA_FILTER} "
            "GROUP BY ticker, snapshot_date, workflow, window_sessions, "
            "data_as_of_date, config_hash "
            "HAVING COUNT(*) > 1"
        ).fetchall()
        group_count = len(groups)
        row_count = sum(g["cnt"] for g in groups)
        return group_count, row_count

    def _compute_latest_dep_missing_columns(
        self,
        conn: sqlite3.Connection,
        config_hash_missing: bool,
        total: int,
    ) -> dict:
        """Compute latest_readiness_dependency when some identity columns are missing.

        When config_hash is missing, every row is legacy so the latest snapshot
        rows must be treated as legacy (depends_on_legacy = True if total > 0).
        """
        if total == 0:
            return {
                "latest_snapshot_date": None,
                "latest_total_rows": 0,
                "latest_legacy_rows": 0,
                "latest_canonical_rows": 0,
                "depends_on_legacy": False,
            }

        row = conn.execute(
            "SELECT snapshot_date, COUNT(*) as total "
            "FROM candidate_observations "
            "GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1"
        ).fetchone()

        if row is None:
            return {
                "latest_snapshot_date": None,
                "latest_total_rows": 0,
                "latest_legacy_rows": 0,
                "latest_canonical_rows": 0,
                "depends_on_legacy": False,
            }

        latest_total = row["total"]
        if config_hash_missing:
            return {
                "latest_snapshot_date": row["snapshot_date"],
                "latest_total_rows": latest_total,
                "latest_legacy_rows": latest_total,
                "latest_canonical_rows": 0,
                "depends_on_legacy": True,
            }

        canonical_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM candidate_observations "
            "WHERE snapshot_date = ? "
            f"AND {_CANONICAL_SCHEMA_FILTER}",
            (row["snapshot_date"],),
        ).fetchone()
        latest_canonical = canonical_row["cnt"] if canonical_row else 0
        latest_legacy = latest_total - latest_canonical

        return {
            "latest_snapshot_date": row["snapshot_date"],
            "latest_total_rows": latest_total,
            "latest_legacy_rows": latest_legacy,
            "latest_canonical_rows": latest_canonical,
            "depends_on_legacy": latest_legacy > 0,
        }

    def _latest_readiness_dependency(self, conn: sqlite3.Connection) -> dict:
        row = conn.execute(
            "SELECT snapshot_date, COUNT(*) as total, "
            f"SUM(CASE WHEN {_CANONICAL_SCHEMA_FILTER} "
            "THEN 1 ELSE 0 END) as canonical, "
            f"SUM(CASE WHEN {_LEGACY_SCHEMA_FILTER} "
            "THEN 1 ELSE 0 END) as legacy "
            "FROM candidate_observations "
            "GROUP BY snapshot_date ORDER BY snapshot_date DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return {
                "latest_snapshot_date": None,
                "latest_total_rows": 0,
                "latest_legacy_rows": 0,
                "latest_canonical_rows": 0,
                "depends_on_legacy": False,
            }
        return {
            "latest_snapshot_date": row["snapshot_date"],
            "latest_total_rows": row["total"],
            "latest_legacy_rows": row["legacy"],
            "latest_canonical_rows": row["canonical"],
            "depends_on_legacy": row["legacy"] > 0,
        }
