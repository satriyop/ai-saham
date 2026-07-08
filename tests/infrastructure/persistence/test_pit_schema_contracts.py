"""
PIT schema contract tests for replay-relevant enrichment tables.

Covers 7 of the 9 tables listed in ADR-038:
  analyst_cache, forward_estimates_cache, ticker_notation_cache,
  stock_meta, company_profile_cache, seasonality_cache, earnings_cache.

The remaining two (company_fundamentals, shareholding_composition) are tested
in tests/infrastructure/browser/test_pit_enrichment.py.

Derived fundamentals constraints (60-day lag, INSERT OR IGNORE, NULL fields,
freshness guard) are covered by
tests/infrastructure/browser/test_historical_fundamentals_backfill.py.

All tests are offline and deterministic (tmp_path SQLite, no network, no cron).
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_forward_estimates import StockbitForwardEstimatesProvider
from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
from src.infrastructure.persistence.sqlite_stock_meta_repository import SQLiteStockMetaRepository
from src.infrastructure.browser.stockbit_company_profile import StockbitCompanyProfileProvider
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.browser.stockbit_earnings import StockbitEarningsProvider
from src.domain.entities.stock_meta import StockMeta

_TICKER = "BBCA"

@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "test.db"

def test_analyst_cache_pit(db_path):
    mock_client = MagicMock()
    provider = StockbitAnalystConsensusProvider(api_client=mock_client, db_path=db_path)
    provider._ensure_schema()
    
    # Insert multiple PIT rows for the same ticker
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO analyst_cache (ticker, buy_count, hold_count, sell_count, fetched_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (_TICKER, 10, 5, 1, "2025-01-01T00:00:00")
        )
        conn.execute(
            "INSERT INTO analyst_cache (ticker, buy_count, hold_count, sell_count, fetched_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (_TICKER, 12, 4, 0, "2025-06-01T00:00:00")
        )

    # Query with as_of_date = 2025-03-01 -> returns the first row
    res = provider._read_cache(_TICKER, as_of_date=date(2025, 3, 1))
    assert res is not None
    assert res.buy_count == 10

    # Query with as_of_date = 2025-07-01 -> returns the second (latest) row
    res = provider._read_cache(_TICKER, as_of_date=date(2025, 7, 1))
    assert res is not None
    assert res.buy_count == 12

    # Query with as_of_date = 2024-01-01 -> returns None
    res = provider._read_cache(_TICKER, as_of_date=date(2024, 1, 1))
    assert res is None


def test_forward_estimates_cache_pit(db_path):
    mock_client = MagicMock()
    provider = StockbitForwardEstimatesProvider(api_client=mock_client, db_path=db_path)
    provider._ensure_schema()
    
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO forward_estimates_cache (ticker, fetched_date, forward_eps_1y, revenue_forward_1y, current_price, forward_pe) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_TICKER, "2025-01-01T00:00:00", 500.0, 1000.0, 6000.0, 12.0)
        )
        conn.execute(
            "INSERT INTO forward_estimates_cache (ticker, fetched_date, forward_eps_1y, revenue_forward_1y, current_price, forward_pe) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_TICKER, "2025-06-01T00:00:00", 550.0, 1100.0, 6500.0, 11.8)
        )

    # Query with as_of_date = 2025-03-01 -> returns the first row
    res = provider._read_cache(_TICKER, require_fresh=False, as_of_date=date(2025, 3, 1))
    assert res is not None
    assert res.forward_eps_1y == 500.0

    # Query with as_of_date = 2025-07-01 -> returns the second row
    res = provider._read_cache(_TICKER, require_fresh=False, as_of_date=date(2025, 7, 1))
    assert res is not None
    assert res.forward_eps_1y == 550.0

    # Query with as_of_date = 2024-01-01 -> returns None
    res = provider._read_cache(_TICKER, require_fresh=False, as_of_date=date(2024, 1, 1))
    assert res is None


def test_ticker_notation_cache_pit(db_path):
    mock_client = MagicMock()
    provider = StockbitTickerNotationProvider(api_client=mock_client, db_path=db_path)
    provider._ensure_schema()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO ticker_notation_cache (ticker, status, tradeable, listing_board, fetched_date, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_TICKER, "active", 1, "Main", "2025-01-01T00:00:00", "2025-01-01T00:00:00")
        )
        conn.execute(
            "INSERT INTO ticker_notation_cache (ticker, status, tradeable, listing_board, fetched_date, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_TICKER, "suspended", 0, "Main", "2025-06-01T00:00:00", "2025-06-01T00:00:00")
        )

    res = provider._read_cache(_TICKER, as_of_date=date(2025, 3, 1))
    assert res is not None
    assert res.status == "active"
    assert res.tradeable is True

    res = provider._read_cache(_TICKER, as_of_date=date(2025, 7, 1))
    assert res is not None
    assert res.status == "suspended"
    assert res.tradeable is False


def test_stock_meta_pit(db_path):
    repo = SQLiteStockMetaRepository(db_path)
    
    meta1 = StockMeta(
        ticker=_TICKER,
        name="Bank Central Asia",
        sector="Financials",
        sector_key="financials",
        industry="Banks",
        industry_key="banks",
        source="yahoo",
        fetched_at=datetime(2025, 1, 1),
        checksum="abc"
    )
    meta2 = StockMeta(
        ticker=_TICKER,
        name="Bank Central Asia TBK",
        sector="Financials",
        sector_key="financials",
        industry="Banks",
        industry_key="banks",
        source="yahoo",
        fetched_at=datetime(2025, 6, 1),
        checksum="abc"
    )
    
    repo.save(meta1)
    repo.save(meta2)
    
    res = repo.get(_TICKER, as_of_date=date(2025, 3, 1))
    assert res is not None
    assert res.name == "Bank Central Asia"
    
    res = repo.get(_TICKER, as_of_date=date(2025, 7, 1))
    assert res is not None
    assert res.name == "Bank Central Asia TBK"


def test_company_profile_cache_pit(db_path):
    mock_client = MagicMock()
    provider = StockbitCompanyProfileProvider(api_client=mock_client, db_path=db_path)
    provider._ensure_schema()
    
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO company_profile_cache (ticker, fetched_date, background, listing_board) "
            "VALUES (?, ?, ?, ?)",
            (_TICKER, "2025-01-01T00:00:00", "Old Bg", "Main")
        )
        conn.execute(
            "INSERT INTO company_profile_cache (ticker, fetched_date, background, listing_board) "
            "VALUES (?, ?, ?, ?)",
            (_TICKER, "2025-06-01T00:00:00", "New Bg", "Main")
        )

    res = provider._read_cache(_TICKER, as_of_date=date(2025, 3, 1), require_fresh=False)
    assert res is not None
    assert res.background == "Old Bg"

    res = provider._read_cache(_TICKER, as_of_date=date(2025, 7, 1), require_fresh=False)
    assert res is not None
    assert res.background == "New Bg"


def test_seasonality_cache_pit(db_path):
    mock_client = MagicMock()
    provider = StockbitSeasonalityProvider(api_client=mock_client, db_path=db_path)
    provider._ensure_schema()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO seasonality_cache (ticker, year, month, avg_return_pct, win_rate_pct, positive_years, total_years, back_years, fetched_month, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_TICKER, 2025, 1, 2.5, 60.0, 6, 10, 10, "2025-01", "2025-01-01T00:00:00")
        )
        conn.execute(
            "INSERT INTO seasonality_cache (ticker, year, month, avg_return_pct, win_rate_pct, positive_years, total_years, back_years, fetched_month, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_TICKER, 2025, 1, 3.2, 70.0, 7, 10, 10, "2025-06", "2025-06-01T00:00:00")
        )

    res = provider._read_cache(_TICKER, 2025, 1, as_of_date=date(2025, 3, 1))
    assert res is not None
    assert res.avg_monthly_return_pct == 2.5

    res = provider._read_cache(_TICKER, 2025, 1, as_of_date=date(2025, 7, 1))
    assert res is not None
    assert res.avg_monthly_return_pct == 3.2


def test_earnings_cache_pit(db_path):
    mock_client = MagicMock()
    provider = StockbitEarningsProvider(api_client=mock_client, db_path=db_path)
    provider._ensure_schema()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO earnings_cache (ticker, year, quarter, eps_actual, eps_estimate, fetched_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_TICKER, 2024, 4, 120.0, 110.0, "2025-01-01T00:00:00")
        )
        conn.execute(
            "INSERT INTO earnings_cache (ticker, year, quarter, eps_actual, eps_estimate, fetched_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_TICKER, 2024, 4, 125.0, 110.0, "2025-06-01T00:00:00")
        )

    res_list = provider._read_cache(_TICKER, quarters=1, as_of_date=date(2025, 3, 1))
    assert len(res_list) == 1
    assert res_list[0].eps_actual == 120.0

    res_list = provider._read_cache(_TICKER, quarters=1, as_of_date=date(2025, 7, 1))
    assert len(res_list) == 1
    assert res_list[0].eps_actual == 125.0
