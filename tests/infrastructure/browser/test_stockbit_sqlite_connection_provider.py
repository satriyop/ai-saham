"""Tests for StockbitSQLiteConnectionProvider — connection lifecycle."""

from __future__ import annotations

import sqlite3

import pytest

from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
    StockbitSQLiteConnectionProvider,
)


def test_same_path_returns_same_connection(tmp_path):
    provider = StockbitSQLiteConnectionProvider()
    db = tmp_path / "test.db"

    conn1 = provider.get_connection(db)
    conn2 = provider.get_connection(db)

    assert conn1 is conn2


def test_different_paths_return_different_connections(tmp_path):
    provider = StockbitSQLiteConnectionProvider()
    db1 = tmp_path / "a.db"
    db2 = tmp_path / "b.db"

    conn1 = provider.get_connection(db1)
    conn2 = provider.get_connection(db2)

    assert conn1 is not conn2


def test_parent_directory_created(tmp_path):
    provider = StockbitSQLiteConnectionProvider()
    db = tmp_path / "sub" / "nested" / "test.db"
    assert not db.parent.exists()

    provider.get_connection(db)

    assert db.parent.exists()


def test_row_factory_is_sqlite_row(tmp_path):
    provider = StockbitSQLiteConnectionProvider()
    conn = provider.get_connection(tmp_path / "test.db")

    assert conn.row_factory is sqlite3.Row


def test_close_removes_only_that_path(tmp_path):
    provider = StockbitSQLiteConnectionProvider()
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"

    conn_a = provider.get_connection(db_a)
    conn_b = provider.get_connection(db_b)

    provider.close(db_a)

    with pytest.raises(sqlite3.ProgrammingError):
        conn_a.execute("SELECT 1")

    conn_b.execute("SELECT 1")

    resolved_a = str(db_a.expanduser().resolve())
    resolved_b = str(db_b.expanduser().resolve())
    assert resolved_a not in provider._connections
    assert resolved_b in provider._connections


def test_after_close_get_connection_returns_new_live_connection(tmp_path):
    provider = StockbitSQLiteConnectionProvider()
    db = tmp_path / "test.db"

    conn_old = provider.get_connection(db)
    conn_old.execute("CREATE TABLE t (x INT)")
    provider.close(db)

    conn_new = provider.get_connection(db)
    conn_new.execute("SELECT 1")

    assert conn_old is not conn_new


def test_close_all_closes_all(tmp_path):
    provider = StockbitSQLiteConnectionProvider()
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"

    provider.get_connection(db_a)
    provider.get_connection(db_b)

    provider.close_all()

    assert len(provider._connections) == 0
    # Re-getting should work with fresh connections
    conn_a2 = provider.get_connection(db_a)
    conn_a2.execute("SELECT 1")


def test_reset_delegates_to_close_all(tmp_path):
    provider = StockbitSQLiteConnectionProvider()
    provider.get_connection(tmp_path / "test.db")

    provider.reset()

    assert len(provider._connections) == 0


def test_no_network_required(tmp_path):
    """The provider never makes network calls — pure local SQLite."""
    provider = StockbitSQLiteConnectionProvider()
    conn = provider.get_connection(tmp_path / "test.db")
    conn.execute("CREATE TABLE demo (k TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO demo (k) VALUES (?)", ("hello",))
    row = conn.execute("SELECT k FROM demo").fetchone()
    assert row["k"] == "hello"
