"""Tests for SqliteMigrationRunner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


def applied_versions(db_path: Path, namespace: str) -> set[int]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT version FROM _schema_migrations WHERE namespace=?", (namespace,)
        ).fetchall()
    return {r[0] for r in rows}


def test_first_run_applies_all_migrations(db_path: Path) -> None:
    migrations = [
        (0, "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)"),
        (1, "ALTER TABLE t ADD COLUMN name TEXT"),
    ]
    SqliteMigrationRunner(db_path).run("t", migrations)

    assert applied_versions(db_path, "t") == {0, 1}
    with sqlite3.connect(str(db_path)) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(t)").fetchall()}
    assert "id" in cols and "name" in cols


def test_second_run_is_noop(db_path: Path) -> None:
    migrations = [
        (0, "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)"),
    ]
    runner = SqliteMigrationRunner(db_path)
    runner.run("t", migrations)
    runner.run("t", migrations)  # must not raise or duplicate

    assert applied_versions(db_path, "t") == {0}


def test_new_migration_applied_on_subsequent_run(db_path: Path) -> None:
    runner = SqliteMigrationRunner(db_path)
    runner.run("t", [(0, "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)")])
    runner.run("t", [
        (0, "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)"),
        (1, "ALTER TABLE t ADD COLUMN extra TEXT"),
    ])

    assert applied_versions(db_path, "t") == {0, 1}


def test_migrations_applied_in_ascending_version_order(db_path: Path) -> None:
    # Pass migrations in reverse order — runner must sort them
    migrations = [
        (2, "ALTER TABLE t ADD COLUMN c TEXT"),
        (0, "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)"),
        (1, "ALTER TABLE t ADD COLUMN b TEXT"),
    ]
    SqliteMigrationRunner(db_path).run("t", migrations)
    assert applied_versions(db_path, "t") == {0, 1, 2}


def test_namespaces_are_independent(db_path: Path) -> None:
    runner = SqliteMigrationRunner(db_path)
    runner.run("a", [(0, "CREATE TABLE IF NOT EXISTS a (id INTEGER PRIMARY KEY)")])
    runner.run("b", [(0, "CREATE TABLE IF NOT EXISTS b (id INTEGER PRIMARY KEY)")])

    assert applied_versions(db_path, "a") == {0}
    assert applied_versions(db_path, "b") == {0}


def test_real_errors_propagate(db_path: Path) -> None:
    runner = SqliteMigrationRunner(db_path)
    with pytest.raises(sqlite3.OperationalError):
        runner.run("t", [(0, "THIS IS NOT VALID SQL AT ALL")])


def test_duplicate_column_is_silently_skipped(db_path: Path) -> None:
    # Simulates an existing DB that already has the column (pre-migration-tracker era)
    runner = SqliteMigrationRunner(db_path)
    runner.run("t", [(0, "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, name TEXT)")])
    # Adding 'name' again would fail in old code; runner must treat it as idempotent
    runner.run("t", [
        (0, "CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, name TEXT)"),
        (1, "ALTER TABLE t ADD COLUMN name TEXT"),  # duplicate column — should not raise
    ])
    assert applied_versions(db_path, "t") == {0, 1}


def test_creates_parent_directories(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "c" / "test.db"
    SqliteMigrationRunner(nested).run(
        "t", [(0, "CREATE TABLE IF NOT EXISTS t (x INTEGER)")]
    )
    assert nested.exists()
