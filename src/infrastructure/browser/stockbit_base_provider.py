"""
StockbitCachingProvider — base class for all Stockbit providers that cache to SQLite.

Centralises the three lines that were duplicated across 13 providers:
  - constructor (api_client + db_path)
  - _get_conn()
  - call to _ensure_schema()

Subclasses implement _ensure_schema() to create their own table(s).

Connection lifecycle is delegated to an injected StockbitSQLiteConnectionProvider
so connection sharing is always explicit.

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
    StockbitSQLiteConnectionProvider,
)

if TYPE_CHECKING:
    import sqlite3

    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient


class StockbitCachingProvider:
    """Base for Stockbit providers that pair live API fetching with a SQLite cache.

    Constructor is fixed: (api_client, db_path, *, connection_provider). Subclasses
    with extra fields (e.g. _mem_cache) must set them before calling
    super().__init__() because the constructor calls _ensure_schema() which may
    indirectly reference them.
    """

    def __init__(
        self,
        api_client: "StockbitApiClient | None",
        db_path: Path | str = Path("data.db"),
        *,
        connection_provider: "StockbitSQLiteConnectionProvider | None" = None,
    ) -> None:
        self._api_client = api_client
        self._db_path = Path(db_path).expanduser()
        self._connection_provider = connection_provider or StockbitSQLiteConnectionProvider()
        self._ensure_schema()

    def _get_conn(self) -> "sqlite3.Connection":
        return self._connection_provider.get_connection(self._db_path)

    def close(self) -> None:
        self._connection_provider.close(self._db_path)

    def _ensure_schema(self) -> None:
        raise NotImplementedError
