"""
Phase D (Rec 16) — date-bound filter for StockbitFundamentalsProvider.

Tests the as_of_date guard that prevents look-ahead bias in backtests.
Uses a real SQLite temp DB to exercise the actual cache logic rather than mocking it.
"""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider

_TICKER = "BBCA"
_1T = 1_000_000_000_000


def _insert_row(db_path: Path, ticker: str, fetched_date: str) -> None:
    """Pre-populate the cache table with a known fetched_date."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO company_fundamentals "
            "(ticker, fetched_date, pe_ratio_ttm, roe_ttm, net_profit_margin, "
            "revenue_yoy_growth, piotroski_f_score, dividend_yield, "
            "week52_high, week52_low, near_52w_high_rank, market_cap_idr, pbv) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticker, fetched_date, 15.0, 22.0, 18.0, 5.0, 7, 2.5, 10000, 7000, 85.0, _1T * 2, 3.0),
        )


@pytest.fixture
def provider(tmp_path) -> StockbitFundamentalsProvider:
    """Provider wired to a temp DB. Broker provider is not needed for cache tests."""
    mock_broker = MagicMock()
    p = StockbitFundamentalsProvider(broker_provider=mock_broker, db_path=tmp_path / "test.db")
    return p


class TestLiveMode:
    """as_of_date=None → existing TTL-based behaviour (no change from Phase A)."""

    def test_returns_data_within_ttl(self, provider, tmp_path):
        fetched_today = datetime.now().isoformat()
        _insert_row(tmp_path / "test.db", _TICKER, fetched_today)
        result = provider.get_fundamentals(_TICKER, as_of_date=None)
        assert result is not None
        assert result.piotroski_f_score == 7

    def test_returns_none_when_cache_stale(self, provider, tmp_path):
        old_date = (datetime.now() - timedelta(days=30)).isoformat()
        _insert_row(tmp_path / "test.db", _TICKER, old_date)
        result = provider.get_fundamentals(_TICKER, as_of_date=None)
        assert result is None  # TTL expired

    def test_returns_none_when_empty_cache(self, provider):
        result = provider.get_fundamentals(_TICKER, as_of_date=None)
        assert result is None


class TestBacktestMode:
    """as_of_date set → date-bound filter; TTL bypassed."""

    def test_returns_data_when_fetched_before_as_of_date(self, provider, tmp_path):
        """fetched 2025-01-01, backtest date 2025-06-01 → data was available."""
        fetched = "2025-01-01T00:00:00"
        _insert_row(tmp_path / "test.db", _TICKER, fetched)
        result = provider.get_fundamentals(_TICKER, as_of_date=date(2025, 6, 1))
        assert result is not None
        assert result.piotroski_f_score == 7

    def test_returns_data_when_fetched_on_exact_as_of_date(self, provider, tmp_path):
        """fetched on the same day as as_of_date → boundary is inclusive."""
        fetched = "2025-06-01T12:00:00"
        _insert_row(tmp_path / "test.db", _TICKER, fetched)
        result = provider.get_fundamentals(_TICKER, as_of_date=date(2025, 6, 1))
        assert result is not None

    def test_returns_none_when_fetched_after_as_of_date(self, provider, tmp_path):
        """fetched 2026-06-23 (today), backtest date 2024-01-15 → look-ahead: reject."""
        fetched = "2026-06-23T00:00:00"
        _insert_row(tmp_path / "test.db", _TICKER, fetched)
        result = provider.get_fundamentals(_TICKER, as_of_date=date(2024, 1, 15))
        assert result is None

    def test_never_fetches_live_in_backtest_mode(self, provider, tmp_path):
        """With as_of_date set and empty cache, must not call the broker API."""
        result = provider.get_fundamentals(_TICKER, as_of_date=date(2024, 1, 15))
        assert result is None
        provider._provider.assert_not_called()

    def test_stale_data_accepted_if_predates_as_of_date(self, provider, tmp_path):
        """A 30-day-old cache row is stale in live mode but valid in backtest mode
        when as_of_date is after the fetch date."""
        fetched = (datetime.now() - timedelta(days=30)).isoformat()
        _insert_row(tmp_path / "test.db", _TICKER, fetched)
        # Would be None in live mode (TTL expired), but valid for a future backtest date
        result = provider.get_fundamentals(_TICKER, as_of_date=date.today())
        assert result is not None  # backtest guard uses date comparison, not TTL


class TestMemoryCacheBypass:
    """In backtest mode, mem_cache must not poison subsequent live calls."""

    def test_backtest_miss_does_not_corrupt_live_cache(self, provider, tmp_path):
        """A backtest miss (as_of_date too early) must not write None to mem_cache."""
        fetched = "2026-06-23T00:00:00"
        _insert_row(tmp_path / "test.db", _TICKER, fetched)

        # Backtest call returns None (future data)
        miss = provider.get_fundamentals(_TICKER, as_of_date=date(2024, 1, 15))
        assert miss is None

        # Live call must still find the fresh row in DB
        live = provider.get_fundamentals(_TICKER, as_of_date=None)
        assert live is not None
