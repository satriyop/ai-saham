"""
Tests for FetchMarketData use case.

These tests use mock providers and repositories to verify:
- Cache-first strategy
- Refresh behavior
- Error handling

All tests run offline with no external dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.use_case.fetch_market_data import (
    FetchMarketDataRequest,
    FetchMarketDataUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_provider import MarketDataProvider
from src.domain.ports.market_data_repository import MarketDataRepository


# --- Test Fixtures ---


def make_candle(ticker: str, days_ago: int) -> Candle:
    """Create a test candle for a given number of days ago."""
    return Candle(
        ticker=ticker,
        date=date.today() - timedelta(days=days_ago),
        open=Decimal("1000.00"),
        high=Decimal("1100.00"),
        low=Decimal("900.00"),
        close=Decimal("1050.00"),
        volume=100000,
    )


class MockProvider(MarketDataProvider):
    """Mock provider for testing."""

    def __init__(self, candles: list[Candle] | None = None):
        self.candles = candles or []
        self.fetch_count = 0

    def fetch_daily_ohlcv(
        self, ticker: str, start_date: date, end_date: date
    ) -> list[Candle]:
        self.fetch_count += 1
        filtered = [c for c in self.candles if start_date <= c.date <= end_date]
        return sorted(filtered, key=lambda c: c.date)


class MockRepository(MarketDataRepository):
    """Mock repository for testing."""

    def __init__(self):
        self._storage: dict[str, list[Candle]] = {}
        self.save_count = 0

    def save_candles(self, candles: list[Candle]) -> None:
        self.save_count += 1
        for c in candles:
            if c.ticker not in self._storage:
                self._storage[c.ticker] = []
            # Upsert
            self._storage[c.ticker] = [
                x for x in self._storage[c.ticker] if x.date != c.date
            ]
            self._storage[c.ticker].append(c)
            self._storage[c.ticker].sort(key=lambda x: x.date)

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        candles = self._storage.get(ticker.upper(), [])
        if start_date:
            candles = [c for c in candles if c.date >= start_date]
        if end_date:
            candles = [c for c in candles if c.date <= end_date]
        return candles

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        date_range = self.get_date_range(ticker)
        if not date_range:
            return False
        return date_range[0] <= start_date and date_range[1] >= end_date

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        candles = self._storage.get(ticker.upper(), [])
        if not candles:
            return None
        return (candles[0].date, candles[-1].date)


# --- Tests ---


class TestFetchMarketDataUseCase:
    """Test FetchMarketData use case behavior."""

    def test_fetch_from_provider_when_cache_empty(self):
        """Should fetch from provider when cache is empty."""
        candles = [make_candle("BBCA", i) for i in range(10)]
        provider = MockProvider(candles)
        repository = MockRepository()

        use_case = FetchMarketDataUseCase(provider, repository)
        request = FetchMarketDataRequest(ticker="BBCA", days=30)

        response = use_case.execute(request)

        assert response.source == "provider"
        assert provider.fetch_count == 1
        assert repository.save_count == 1
        assert len(response.candles) > 0

    def test_use_cache_when_data_exists(self):
        """Should use cache when data exists and covers range."""
        candles = [make_candle("BBCA", i) for i in range(400)]
        provider = MockProvider(candles)
        repository = MockRepository()

        # Pre-populate cache
        repository.save_candles(candles)

        use_case = FetchMarketDataUseCase(provider, repository)
        request = FetchMarketDataRequest(ticker="BBCA", days=365)

        response = use_case.execute(request)

        assert response.source == "cache"
        assert provider.fetch_count == 0  # Provider not called

    def test_refresh_bypasses_cache(self):
        """Should fetch from provider when refresh=True."""
        candles = [make_candle("BBCA", i) for i in range(400)]
        provider = MockProvider(candles)
        repository = MockRepository()

        # Pre-populate cache
        repository.save_candles(candles)

        use_case = FetchMarketDataUseCase(provider, repository)
        request = FetchMarketDataRequest(ticker="BBCA", days=365, refresh=True)

        response = use_case.execute(request)

        assert response.source == "provider"
        assert provider.fetch_count == 1

    def test_normalizes_ticker_to_uppercase(self):
        """Should normalize ticker to uppercase."""
        candles = [make_candle("BBCA", i) for i in range(10)]
        provider = MockProvider(candles)
        repository = MockRepository()

        use_case = FetchMarketDataUseCase(provider, repository)
        request = FetchMarketDataRequest(ticker="bbca", days=30)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"

    def test_empty_ticker_raises_error(self):
        """Should raise ValueError for empty ticker."""
        provider = MockProvider()
        repository = MockRepository()

        use_case = FetchMarketDataUseCase(provider, repository)
        request = FetchMarketDataRequest(ticker="", days=30)

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_whitespace_ticker_raises_error(self):
        """Should raise ValueError for whitespace-only ticker."""
        provider = MockProvider()
        repository = MockRepository()

        use_case = FetchMarketDataUseCase(provider, repository)
        request = FetchMarketDataRequest(ticker="   ", days=30)

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_response_contains_date_range(self):
        """Response should include date range of returned data."""
        candles = [make_candle("BBCA", i) for i in range(10)]
        provider = MockProvider(candles)
        repository = MockRepository()

        use_case = FetchMarketDataUseCase(provider, repository)
        request = FetchMarketDataRequest(ticker="BBCA", days=30)

        response = use_case.execute(request)

        assert response.date_range is not None
        assert response.date_range[0] <= response.date_range[1]

    def test_empty_response_when_no_data(self):
        """Should return empty response when no data available."""
        provider = MockProvider([])  # No data
        repository = MockRepository()

        use_case = FetchMarketDataUseCase(provider, repository)
        request = FetchMarketDataRequest(ticker="XXXX", days=30)

        response = use_case.execute(request)

        assert response.candles == []
        assert response.count == 0
        assert response.date_range is None
