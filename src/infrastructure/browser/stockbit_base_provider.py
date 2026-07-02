"""
StockbitCachingProvider — base class for all Stockbit providers that cache to SQLite.

Centralises the three lines that were duplicated across 13 providers:
  - constructor (api_client + db_path)
  - _get_conn()
  - call to _ensure_schema()

Subclasses implement _ensure_schema() to create their own table(s).

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

# One live connection per resolved db_path, shared across all providers in a process.
# CLI processes are short-lived; connections close on exit. Tests use unique tmp_path dirs
# so each test gets its own path key and there is no cross-test state.
_conn_registry: dict[str, sqlite3.Connection] = {}


class StockbitCachingProvider:
    """Base for Stockbit providers that pair live API fetching with a SQLite cache.

    Constructor is fixed: (api_client, db_path). Subclasses with extra fields
    (e.g. _mem_cache) must set them before calling super().__init__() because
    the constructor calls _ensure_schema() which may indirectly reference them.
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path | str = Path("data.db"),
    ) -> None:
        self._api_client = api_client
        self._db_path = Path(db_path).expanduser()
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        key = str(self._db_path.resolve())
        conn = _conn_registry.get(key)
        if conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            _conn_registry[key] = conn
        return conn

    def _ensure_schema(self) -> None:
        raise NotImplementedError
