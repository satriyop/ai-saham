import sqlite3
from datetime import date

import pytest

from src.domain.value_objects.insider_transaction import InsiderTransaction
from src.infrastructure.browser.stockbit_insider_cache import StockbitInsiderCache


@pytest.fixture
def cache(tmp_path):
    conn = sqlite3.connect(tmp_path / "stockbit.db")
    conn.row_factory = sqlite3.Row
    store = StockbitInsiderCache(conn)
    store.ensure_schema()
    return store


def _txn(
    *,
    ticker: str = "BBCA",
    name: str = "Jane Doe",
    role: str = "DIREKTUR",
    action_type: str = "BUY",
    shares: int = 1000,
    price: float = 5000.0,
    transaction_date: date = date(2026, 5, 20),
) -> InsiderTransaction:
    return InsiderTransaction(
        ticker=ticker,
        name=name,
        role=role,
        action_type=action_type,
        shares=shares,
        price=price,
        transaction_date=transaction_date,
        ownership_before_pct=0.0,
        ownership_after_pct=0.0,
    )


def test_ensure_schema_creates_usable_schema(cache):
    row = cache._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='insider_cache'"
    ).fetchone()
    assert row is not None


_WIDE_FROM = date(2000, 1, 1)
_WIDE_TO = date(2099, 12, 31)


def test_write_then_read_returns_transactions(cache):
    cache.write("BBCA", [_txn(shares=1500)])

    results = cache.read("BBCA", _WIDE_FROM, _WIDE_TO, "ALL")

    assert len(results) == 1
    assert results[0].shares == 1500
    assert results[0].name == "Jane Doe"


def test_empty_write_creates_none_sentinel_and_read_returns_empty(cache):
    cache.write("BBCA", [])

    row = cache._conn.execute(
        "SELECT 1 FROM insider_cache WHERE ticker='BBCA' AND name='__NONE__'"
    ).fetchone()
    assert row is not None
    assert cache.read("BBCA", _WIDE_FROM, _WIDE_TO, "ALL") == []


def test_no_result_sentinel_does_not_hide_older_valid_pit_rows(cache):
    cache._conn.execute("""
        INSERT OR REPLACE INTO insider_cache
            (ticker, name, role, action_type, shares, price, transaction_date,
             ownership_before_pct, ownership_after_pct, fetched_date)
        VALUES ('BBCA', 'Jane Doe', 'DIREKTUR', 'BUY', 1000, 5000, '2026-05-20',
                0, 0, '2026-06-01')
        """)
    cache._conn.execute("""
        INSERT OR REPLACE INTO insider_cache
            (ticker, name, role, action_type, shares, price, transaction_date,
             ownership_before_pct, ownership_after_pct, fetched_date)
        VALUES ('BBCA', '__NONE__', '', 'NONE', 0, 0, '1970-01-01', 0, 0, '2026-06-15')
        """)

    results = cache.read("BBCA", _WIDE_FROM, _WIDE_TO, "ALL", as_of_date=date(2026, 6, 10))

    assert len(results) == 1
    assert results[0].name == "Jane Doe"


def test_sentinel_with_unrelated_real_row_does_not_leak_older_scoped_row(cache):
    """Regression: a __NONE__ sentinel at the latest fetched_date must only
    suppress older rows matching the *requested* range/action scope, not
    suppress based on "any real row exists at all" — otherwise an unrelated
    real row from a different fetch leaks stale data for the requested scope.
    """
    cache._conn.execute("""
        INSERT OR REPLACE INTO insider_cache
            (ticker, name, role, action_type, shares, price, transaction_date,
             ownership_before_pct, ownership_after_pct, fetched_date)
        VALUES ('BBCA', 'Old Seller', 'DIREKTUR', 'SELL', 1000, 5000, '2026-05-20',
                0, 0, '2026-06-01')
        """)
    cache._conn.execute("""
        INSERT OR REPLACE INTO insider_cache
            (ticker, name, role, action_type, shares, price, transaction_date,
             ownership_before_pct, ownership_after_pct, fetched_date)
        VALUES ('BBCA', 'Buyer Latest', 'DIREKTUR', 'BUY', 2000, 5100, '2026-06-10',
                0, 0, '2026-06-15')
        """)
    cache._conn.execute("""
        INSERT OR REPLACE INTO insider_cache
            (ticker, name, role, action_type, shares, price, transaction_date,
             ownership_before_pct, ownership_after_pct, fetched_date)
        VALUES ('BBCA', '__NONE__', '', 'NONE', 0, 0, '1970-01-01', 0, 0, '2026-06-15')
        """)

    results = cache.read(
        "BBCA",
        _WIDE_FROM,
        _WIDE_TO,
        "SELL",
        as_of_date=date(2026, 6, 20),
    )

    assert results == []


def test_as_of_date_returns_only_latest_eligible_snapshot(cache):
    cache._conn.execute("""
        INSERT OR REPLACE INTO insider_cache
            (ticker, name, role, action_type, shares, price, transaction_date,
             ownership_before_pct, ownership_after_pct, fetched_date)
        VALUES ('BBCA', 'Jane Doe', 'DIREKTUR', 'BUY', 1000, 5000, '2026-05-20',
                0, 0, '2026-06-01')
        """)
    cache._conn.execute("""
        INSERT OR REPLACE INTO insider_cache
            (ticker, name, role, action_type, shares, price, transaction_date,
             ownership_before_pct, ownership_after_pct, fetched_date)
        VALUES ('BBCA', 'Jane Doe', 'DIREKTUR', 'BUY', 2000, 5100, '2026-05-20',
                0, 0, '2026-06-15')
        """)
    cache._conn.execute("""
        INSERT OR REPLACE INTO insider_cache
            (ticker, name, role, action_type, shares, price, transaction_date,
             ownership_before_pct, ownership_after_pct, fetched_date)
        VALUES ('BBCA', 'Jane Doe', 'DIREKTUR', 'BUY', 3000, 5200, '2026-05-20',
                0, 0, '2026-07-01')
        """)

    results = cache.read("BBCA", _WIDE_FROM, _WIDE_TO, "ALL", as_of_date=date(2026, 6, 20))

    assert len(results) == 1
    assert results[0].shares == 2000


def test_legacy_schema_migration_preserves_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE insider_cache (
                ticker                TEXT NOT NULL,
                name                  TEXT NOT NULL DEFAULT '',
                role                  TEXT NOT NULL DEFAULT '',
                action_type           TEXT NOT NULL,
                shares                INTEGER NOT NULL DEFAULT 0,
                price                 REAL NOT NULL DEFAULT 0,
                transaction_date      TEXT NOT NULL,
                ownership_before_pct  REAL NOT NULL DEFAULT 0,
                ownership_after_pct   REAL NOT NULL DEFAULT 0,
                fetched_date          TEXT NOT NULL,
                PRIMARY KEY (ticker, name, transaction_date, action_type)
            )
            """)
        conn.execute("""
            INSERT INTO insider_cache
                (ticker, name, role, action_type, shares, price, transaction_date,
                 ownership_before_pct, ownership_after_pct, fetched_date)
            VALUES ('BBCA', 'Jane Doe', 'DIREKTUR', 'BUY', 1000, 5000,
                    '2026-05-20', 0, 0, '2026-06-01')
            """)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    store = StockbitInsiderCache(conn)
    store.ensure_schema()

    pk_cols = [
        row["name"]
        for row in sorted(
            conn.execute("PRAGMA table_info(insider_cache)").fetchall(),
            key=lambda r: r["pk"],
        )
        if row["pk"] > 0
    ]
    count = conn.execute("SELECT COUNT(*) FROM insider_cache").fetchone()[0]

    assert pk_cols == [
        "ticker",
        "name",
        "transaction_date",
        "action_type",
        "fetched_date",
    ]
    assert count == 1


def test_is_fresh_true_for_today_and_false_for_stale(cache):
    cache.write("BBCA", [_txn()])
    assert cache.is_fresh("BBCA") is True

    cache._conn.execute("UPDATE insider_cache SET fetched_date='2020-01-01' WHERE ticker='BBCA'")
    assert cache.is_fresh("BBCA") is False
