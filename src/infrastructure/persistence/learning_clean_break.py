"""One-shot destructive transition to the database-owned learning schema.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.domain.value_objects.learning_artifacts import LearningContractError
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    create_learning_schema,
)

LEGACY_TABLES = (
    "candidate_observations",
    "candidate_observations_quarantine",
    "observation_risk_assessments",
    "signal_forward_labels",
    "signal_forward_labels_quarantine",
)
LEGACY_MIGRATION_NAMESPACES = (
    "candidate_observations",
    "observation_risk_assessments",
    "signal_forward_labels",
)
LEARNING_TABLES = (
    "learning_observations",
    "learning_track_snapshots",
    "learning_outcome_labels",
    "learning_evaluations",
    "learning_policy_proposals",
    "learning_policy_validations",
    "learning_policy_applications",
)


@dataclass(frozen=True)
class LearningCleanBreakReport:
    before_counts: dict[str, int | None]
    deleted_migration_records: int
    created_tables: tuple[str, ...]
    foreign_key_violations: int


def apply_learning_clean_break(db_path: Path) -> LearningCleanBreakReport:
    """Drop the five retired tables and create the seven canonical tables.

    The entire schema transition is one ``BEGIN IMMEDIATE`` transaction. Any
    missing postcondition or foreign-key violation rolls it back.
    """

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise LearningContractError("SQLite foreign keys must be enabled")
        connection.execute("BEGIN IMMEDIATE")
        before = {
            table: _count_or_none(connection, table) for table in LEGACY_TABLES
        }

        # Children first. Every statement names one exact approved table.
        for table in (
            "observation_risk_assessments",
            "signal_forward_labels",
            "signal_forward_labels_quarantine",
            "candidate_observations",
            "candidate_observations_quarantine",
        ):
            connection.execute(f'DROP TABLE IF EXISTS "{table}"')

        deleted_migrations = 0
        if _table_exists(connection, "_schema_migrations"):
            placeholders = ",".join("?" for _ in LEGACY_MIGRATION_NAMESPACES)
            cursor = connection.execute(
                "DELETE FROM _schema_migrations "
                f"WHERE namespace IN ({placeholders})",
                LEGACY_MIGRATION_NAMESPACES,
            )
            deleted_migrations = cursor.rowcount

        create_learning_schema(connection)
        remaining_legacy = [
            table for table in LEGACY_TABLES if _table_exists(connection, table)
        ]
        if remaining_legacy:
            raise LearningContractError(
                f"legacy learning tables remain: {remaining_legacy}"
            )
        missing_learning = [
            table for table in LEARNING_TABLES if not _table_exists(connection, table)
        ]
        if missing_learning:
            raise LearningContractError(
                f"canonical learning tables missing: {missing_learning}"
            )
        nonempty_learning = {
            table: _count_or_none(connection, table)
            for table in LEARNING_TABLES
            if _count_or_none(connection, table) != 0
        }
        if nonempty_learning:
            raise LearningContractError(
                f"new learning tables must start empty: {nonempty_learning}"
            )
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise LearningContractError(
                f"foreign-key check failed with {len(violations)} violations"
            )
        connection.commit()
        return LearningCleanBreakReport(
            before_counts=before,
            deleted_migration_records=deleted_migrations,
            created_tables=LEARNING_TABLES,
            foreign_key_violations=0,
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def _count_or_none(
    connection: sqlite3.Connection, table: str
) -> int | None:
    if not _table_exists(connection, table):
        return None
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
