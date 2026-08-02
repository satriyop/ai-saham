"""
Module-global-free SQLite connection provider for Stockbit caching providers.

Owns one connection per resolved DB path in instance state only.

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


class StockbitSQLiteConnectionProvider:
    """Instance-owned connection pool keyed by resolved DB path.

    Each provider object holds its own mapping — no module-level state.

    - key: str(Path(db_path).expanduser().resolve())
    - parent directory auto-created before connect
    - row_factory = sqlite3.Row
    - check_same_thread = False
    - Same resolved path -> same connection object (within the same provider instance)
    """

    def __init__(self, *, initialize_schema: bool = True) -> None:
        self._connections: dict[str, sqlite3.Connection] = {}
        self._initialize_schema = initialize_schema

    @property
    def initialize_schema(self) -> bool:
        """Whether cache providers may run constructor schema setup."""
        return self._initialize_schema

    def get_connection(self, db_path: Path | str) -> sqlite3.Connection:
        path = Path(db_path).expanduser().resolve()
        key = str(path)
        conn = self._connections.get(key)
        if conn is None:
            if not self._initialize_schema and not path.is_file():
                raise FileNotFoundError(f"SQLite cache is unavailable: {path}")
            if self._initialize_schema:
                path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            if not self._initialize_schema:
                conn.execute("PRAGMA query_only = ON")
            self._connections[key] = conn
        return conn

    def close(self, db_path: Path | str) -> None:
        key = str(Path(db_path).expanduser().resolve())
        conn = self._connections.pop(key, None)
        if conn is not None:
            conn.close()

    def close_all(self) -> None:
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()

    def reset(self) -> None:
        self.close_all()
