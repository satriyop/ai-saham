"""
Phase D (Rec 16) — date-bound filter for StockbitShareholdingProvider.

Tests the as_of_date guard using report_date (IDX filing date) as the boundary,
with fallback to fetched_date when report_date is absent.
"""

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider

_TICKER = "BBCA"


def _insert_row(
    db_path: Path,
    ticker: str,
    fetched_date: str,
    report_date: str | None = None,
) -> None:
    """Pre-populate the shareholding cache with known dates."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO shareholding_composition "
            "(ticker, fetched_date, report_date, institution_pct, individual_pct, "
            "top_holder_name, top_holder_pct, total_shares, total_shares_formatted) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (ticker, fetched_date, report_date, 65.0, 25.0, "DWIMURIA", 30.0, 100_000_000, "100M"),
        )


@pytest.fixture
def provider(tmp_path) -> StockbitShareholdingProvider:
    mock_broker = MagicMock()
    return StockbitShareholdingProvider(api_client=mock_broker, db_path=tmp_path / "test.db")


class TestLiveMode:
    def test_returns_data_within_refresh_ttl(self, provider, tmp_path):
        _insert_row(tmp_path / "test.db", _TICKER, datetime.now().isoformat(), "2026-03-31")
        result = provider.get_composition(_TICKER, as_of_date=None)
        assert result is not None
        assert result.institution_pct == 65.0

    def test_returns_last_known_row_when_past_refresh_ttl(self, provider, tmp_path):
        """Ownership is long-term — display must not blank after refresh TTL."""
        old = (datetime.now() - timedelta(days=30)).isoformat()
        _insert_row(tmp_path / "test.db", _TICKER, old, "2026-03-31")
        result = provider.get_composition(_TICKER, as_of_date=None)
        assert result is not None
        assert result.institution_pct == 65.0
        assert result.top_holder_name == "DWIMURIA"
        # Cache-only (api may exist on mock but fetch path unused when we short-circuit
        # — with api_client mock and stale cache, get_composition may try fetch.
        # Force cache-only behaviour for this assertion:
        provider._api_client = None
        result2 = provider.read_cached(_TICKER)
        assert result2 is not None
        assert result2.institution_pct == 65.0

    def test_cache_only_read_ignores_refresh_ttl(self, provider, tmp_path):
        old = (datetime.now() - timedelta(days=120)).isoformat()
        _insert_row(tmp_path / "test.db", _TICKER, old, "2026-03-31")
        assert provider.read_cached(_TICKER) is not None
        assert provider._is_cache_fresh(_TICKER) is False


class TestBacktestModeWithReportDate:
    """When report_date is present, it is the authoritative filing boundary."""

    def test_returns_data_when_report_date_before_as_of_date(self, provider, tmp_path):
        """Q1 filing (2025-03-31) used in backtest at 2025-06-01 → available."""
        _insert_row(tmp_path / "test.db", _TICKER, "2025-04-15T00:00:00", "2025-03-31")
        result = provider.get_composition(_TICKER, as_of_date=date(2025, 6, 1))
        assert result is not None

    def test_returns_data_on_exact_report_date(self, provider, tmp_path):
        """Boundary is inclusive: report_date == as_of_date → data available."""
        _insert_row(tmp_path / "test.db", _TICKER, "2025-04-15T00:00:00", "2025-06-01")
        result = provider.get_composition(_TICKER, as_of_date=date(2025, 6, 1))
        assert result is not None

    def test_returns_none_when_report_date_after_as_of_date(self, provider, tmp_path):
        """Q2 filing (2025-06-30) used in backtest at 2025-01-15 → look-ahead: reject."""
        _insert_row(tmp_path / "test.db", _TICKER, "2026-06-23T00:00:00", "2025-06-30")
        result = provider.get_composition(_TICKER, as_of_date=date(2025, 1, 15))
        assert result is None


class TestBacktestModeFallbackToFetchedDate:
    """When report_date is absent, falls back to fetched_date as boundary."""

    def test_returns_data_when_fetched_before_as_of_date(self, provider, tmp_path):
        _insert_row(tmp_path / "test.db", _TICKER, "2024-12-01T00:00:00", None)
        result = provider.get_composition(_TICKER, as_of_date=date(2025, 6, 1))
        assert result is not None

    def test_returns_none_when_fetched_after_as_of_date(self, provider, tmp_path):
        _insert_row(tmp_path / "test.db", _TICKER, "2026-06-23T00:00:00", None)
        result = provider.get_composition(_TICKER, as_of_date=date(2024, 1, 15))
        assert result is None


class TestBacktestNeverFetchesLive:
    def test_empty_cache_in_backtest_mode_does_not_call_api(self, provider):
        result = provider.get_composition(_TICKER, as_of_date=date(2024, 1, 15))
        assert result is None
        provider._api_client.assert_not_called()


class TestMemoryCacheBypass:
    def test_backtest_miss_does_not_corrupt_live_cache(self, provider, tmp_path):
        _insert_row(
            tmp_path / "test.db",
            _TICKER,
            (datetime.now() - timedelta(days=1)).isoformat(),
            "2026-03-31",
        )

        # Backtest call: report_date 2026-03-31 > as_of_date 2025-01-01 → None
        miss = provider.get_composition(_TICKER, as_of_date=date(2025, 1, 1))
        assert miss is None

        # Live call must still work (fresh row exists)
        live = provider.get_composition(_TICKER, as_of_date=None)
        assert live is not None
