import sqlite3
from datetime import date, datetime, timedelta

import pytest

from src.domain.value_objects.earnings_record import EarningsRecord
from src.infrastructure.browser.stockbit_earnings_cache import StockbitEarningsCache


@pytest.fixture
def cache(tmp_path):
    conn = sqlite3.connect(tmp_path / "stockbit.db")
    conn.row_factory = sqlite3.Row
    store = StockbitEarningsCache(conn)
    store.ensure_schema()
    return store


def _record(
    *,
    ticker: str = "BBCA",
    year: int = 2026,
    quarter: int = 1,
    eps_actual: float = 119.12,
    fetched_at: datetime | None = None,
) -> EarningsRecord:
    return EarningsRecord(
        ticker=ticker,
        year=year,
        quarter=quarter,
        eps_actual=eps_actual,
        eps_estimate=None,
        eps_surprise_pct=None,
        eps_yoy_change=None,
        eps_prev_year=None,
        fetched_at=fetched_at or datetime.now(),
    )


def test_ensure_schema_creates_usable_schema(cache):
    row = cache._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='earnings_cache'"
    ).fetchone()
    assert row is not None


def test_write_record_then_read_returns_records(cache):
    cache.write_record(_record(eps_actual=101.0))

    results = cache.read("BBCA")

    assert len(results) == 1
    assert results[0].eps_actual == pytest.approx(101.0)


def test_read_returns_latest_fetched_row_per_ticker_year_quarter(cache):
    cache.write_record(_record(quarter=1, eps_actual=101.0, fetched_at=datetime(2026, 6, 1, 9)))
    cache.write_record(_record(quarter=1, eps_actual=111.0, fetched_at=datetime(2026, 6, 10, 9)))
    cache.write_record(_record(quarter=2, eps_actual=102.0, fetched_at=datetime(2026, 6, 10, 9)))

    results = cache.read("BBCA")

    by_quarter = {r.quarter: r.eps_actual for r in results}
    assert by_quarter == {1: pytest.approx(111.0), 2: pytest.approx(102.0)}
    assert results[0].quarter == 2  # newest first


def test_read_as_of_date_excludes_future_fetched_snapshots(cache):
    cache.write_record(_record(quarter=1, eps_actual=101.0, fetched_at=datetime(2026, 6, 1, 9)))
    cache.write_record(_record(quarter=2, eps_actual=102.0, fetched_at=datetime(2026, 6, 10, 9)))

    results = cache.read("BBCA", as_of_date=date(2026, 6, 6))

    assert len(results) == 1
    assert results[0].quarter == 1


def test_read_single_returns_latest_row_for_requested_quarter(cache):
    cache.write_record(_record(quarter=1, eps_actual=101.0, fetched_at=datetime(2026, 6, 1, 9)))
    cache.write_record(_record(quarter=1, eps_actual=111.0, fetched_at=datetime(2026, 6, 10, 9)))

    result = cache.read_single("BBCA", 2026, 1)

    assert result is not None
    assert result.eps_actual == pytest.approx(111.0)


def test_read_single_returns_none_when_missing(cache):
    assert cache.read_single("BBCA", 2026, 1) is None


def test_is_row_fresh_true_within_ttl_false_when_stale(cache):
    cache.write_record(_record(fetched_at=datetime.now()))
    assert cache.is_row_fresh("BBCA", 2026, 1) is True

    cache.write_record(_record(fetched_at=datetime.now() - timedelta(days=8)))
    assert cache.is_row_fresh("BBCA", 2026, 1) is True  # freshest row still within TTL

    cache._conn.execute("DELETE FROM earnings_cache")
    cache.write_record(_record(fetched_at=datetime.now() - timedelta(days=8)))
    assert cache.is_row_fresh("BBCA", 2026, 1) is False


def test_is_fresh_true_when_recent_false_when_stale(cache):
    assert cache.is_fresh("BBCA") is False

    cache.write_record(_record(fetched_at=datetime.now()))
    assert cache.is_fresh("BBCA") is True

    cache._conn.execute("DELETE FROM earnings_cache")
    cache.write_record(_record(fetched_at=datetime.now() - timedelta(days=8)))
    assert cache.is_fresh("BBCA") is False


def test_legacy_migration_insert_is_safe_and_preserves_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE earnings_cache (
                ticker TEXT NOT NULL,
                year INTEGER NOT NULL,
                quarter INTEGER NOT NULL,
                eps_actual REAL,
                eps_estimate REAL,
                eps_surprise_pct REAL,
                eps_yoy_change REAL,
                eps_prev_year REAL,
                fetched_date TEXT NOT NULL,
                PRIMARY KEY (ticker, year, quarter)
            )
            """)
        conn.execute("""
            INSERT INTO earnings_cache
                (ticker, year, quarter, eps_actual, eps_estimate, eps_surprise_pct,
                 eps_yoy_change, eps_prev_year, fetched_date)
            VALUES ('BBCA', 2026, 1, 101.0, NULL, NULL, NULL, NULL, '2026-06-01T09:00:00')
            """)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    store = StockbitEarningsCache(conn)
    store.ensure_schema()
    store.ensure_schema()  # idempotent on an already-migrated schema

    pk_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(earnings_cache)")
        if int(row["pk"]) > 0
    }
    result = store.read("BBCA", as_of_date=date(2026, 6, 6))

    assert pk_columns == set()
    assert len(result) == 1
    assert result[0].eps_actual == pytest.approx(101.0)
