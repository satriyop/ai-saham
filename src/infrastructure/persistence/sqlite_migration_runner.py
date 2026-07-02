"""
SqliteMigrationRunner — versioned, run-once schema migration runner for SQLite.

Tracks applied migrations in a `_schema_migrations` table keyed by
(namespace, version). Each namespace corresponds to one provider's table group.

Usage:
    runner = SqliteMigrationRunner(db_path)
    runner.run("bandar_detector", [
        (0, "CREATE TABLE IF NOT EXISTS bandar_detector (...)"),
        (1, "ALTER TABLE bandar_detector ADD COLUMN vwap REAL"),
    ])

Migrations are applied in ascending version order. Already-applied versions
are skipped. Real errors (not duplicate-column OperationalErrors) propagate
so callers can log and handle them explicitly.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SqliteMigrationRunner:
    _CREATE_MIGRATIONS_TABLE = """
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            namespace  TEXT    NOT NULL,
            version    INTEGER NOT NULL,
            applied_at TEXT    DEFAULT (datetime('now')),
            PRIMARY KEY (namespace, version)
        )
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    def run(self, namespace: str, migrations: list[tuple[int, str]]) -> None:
        """Apply any unapplied migrations in ascending version order.

        Idempotent — already-applied versions are silently skipped.
        "Duplicate column name" errors are also skipped so ADD COLUMN
        statements are safe to run against DBs that pre-date migration tracking.
        All other errors propagate; callers should wrap in try/except and log.
        """
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute(self._CREATE_MIGRATIONS_TABLE)
            applied = self._applied_versions(conn, namespace)
            for version, sql in sorted(migrations, key=lambda x: x[0]):
                if version not in applied:
                    try:
                        conn.execute(sql)
                    except sqlite3.OperationalError as exc:
                        if "duplicate column name" not in str(exc).lower():
                            raise
                    conn.execute(
                        "INSERT INTO _schema_migrations (namespace, version) VALUES (?, ?)",
                        (namespace, version),
                    )

    def _applied_versions(self, conn: sqlite3.Connection, namespace: str) -> set[int]:
        rows = conn.execute(
            "SELECT version FROM _schema_migrations WHERE namespace = ?",
            (namespace,),
        ).fetchall()
        return {row[0] for row in rows}
