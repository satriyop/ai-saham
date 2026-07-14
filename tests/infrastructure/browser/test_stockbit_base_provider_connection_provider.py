"""Tests for StockbitCachingProvider — connection_provider integration."""

from __future__ import annotations

from src.infrastructure.browser.stockbit_base_provider import StockbitCachingProvider
from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
    StockbitSQLiteConnectionProvider,
)


class _TestProvider(StockbitCachingProvider):
    """Minimal subclass that creates a test_data table in _ensure_schema."""

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS test_data (k TEXT PRIMARY KEY, v TEXT)"
        )


def test_ensure_schema_runs_during_construction(tmp_path):
    db = tmp_path / "test.db"
    provider = _TestProvider(api_client=None, db_path=db)

    conn = provider._get_conn()
    result = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='test_data'"
    ).fetchone()
    assert result is not None


def test_two_providers_share_connection(tmp_path):
    db = tmp_path / "shared.db"
    cp = StockbitSQLiteConnectionProvider()

    p1 = _TestProvider(api_client=None, db_path=db, connection_provider=cp)
    p2 = _TestProvider(api_client=None, db_path=db, connection_provider=cp)

    assert p1._get_conn() is p2._get_conn()


def test_data_written_by_one_provider_visible_by_other(tmp_path):
    db = tmp_path / "shared.db"
    cp = StockbitSQLiteConnectionProvider()

    p1 = _TestProvider(api_client=None, db_path=db, connection_provider=cp)
    p2 = _TestProvider(api_client=None, db_path=db, connection_provider=cp)

    p1._get_conn().execute(
        "INSERT OR REPLACE INTO test_data (k, v) VALUES (?, ?)", ("key1", "value1")
    )

    row = p2._get_conn().execute("SELECT v FROM test_data WHERE k=?", ("key1",)).fetchone()
    assert row is not None
    assert row["v"] == "value1"


def test_construction_without_connection_provider(tmp_path):
    db = tmp_path / "standalone.db"
    provider = _TestProvider(api_client=None, db_path=db)

    conn = provider._get_conn()
    conn.execute("SELECT 1")
    assert provider._connection_provider is not None


def test_close_closes_connection(tmp_path):
    db = tmp_path / "close.db"
    provider = _TestProvider(api_client=None, db_path=db)

    conn_before = provider._get_conn()
    provider.close()

    # After close, a new get_connection returns a different connection
    conn_after = provider._get_conn()
    assert conn_before is not conn_after
    conn_after.execute("SELECT 1")
