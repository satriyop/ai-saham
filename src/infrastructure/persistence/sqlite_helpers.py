"""Shared SQLite connection + read-time introspection helpers.

Two connection modes only:

- ``connect_readonly`` opens with SQLite URI ``mode=ro`` and never creates
  files, tables, or columns — use it for audit/reconciliation readers that
  must stay transitively read-only.
- ``connect_readwrite`` creates parent directories and returns a
  ``sqlite3.Row`` connection — use it for owning repositories that manage
  their own schema.

Introspection helpers are read-only queries over an existing connection.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_readonly(db_path: Path | str) -> sqlite3.Connection:
    """Open ``db_path`` read-only (URI ``mode=ro``); never creates anything."""
    uri = f"file:{db_path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def connect_readwrite(db_path: Path | str) -> sqlite3.Connection:
    """Open ``db_path`` for writing, creating parent dirs; rows are ``sqlite3.Row``."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def missing_columns(columns: set[str], required: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(c for c in required if c not in columns)


def rows_as_dicts(conn: sqlite3.Connection, query: str) -> tuple[dict, ...]:
    cursor = conn.execute(query)
    columns = [description[0] for description in cursor.description]
    return tuple(dict(zip(columns, row)) for row in cursor.fetchall())
