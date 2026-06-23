"""
Tests for ComputeRSI use case.

These tests use mock repository to verify:
- Orchestration between repository and indicator
- Warm-up buffer handling (over-fetch and slice)
- Request/response DTOs
- Error handling
- Edge cases

All tests run offline with no external dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.use_case.compute_rsi_use_case import (
    ComputeRSIRequest,
    ComputeRSIResponse,
    ComputeRSIUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository

# --- Test Fixtures ---


def make_candle(ticker: str, days_ago: int, price: str = "100.00") -> Candle:
    """Create a test candle."""
    return Candle(
        ticker=ticker,
        date=date.today() - timedelta(days=days_ago),
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        volume=100000,
    )


def make_varying_candles(ticker: str, count: int) -> list[Candle]:
    """Create candles with varying prices for RSI calculation."""
    # Alternate up/down to generate both gains and losses
    candles = []
    for i in range(count - 1, -1, -1):
        price = "100.00" if i % 2 == 0 else "110.00"
        candles.append(make_candle(ticker, i, price))
    return candles


class MockRepository(MarketDataRepository):
    """Mock repository for testing."""

    def __init__(self, candles: list[Candle] | None = None):
        self._candles = candles or []

    def get_candles(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Candle]:
        filtered = [c for c in self._candles if c.ticker == ticker.upper()]
        if start_date:
            filtered = [c for c in filtered if c.date >= start_date]
        if end_date:
            filtered = [c for c in filtered if c.date <= end_date]
        return sorted(filtered, key=lambda c: c.date)

    def save_candles(self, candles: list[Candle]) -> None:
        pass

    def has_data(self, ticker: str, start_date: date, end_date: date) -> bool:
        return len(self._candles) > 0

    def get_date_range(self, ticker: str) -> tuple[date, date] | None:
        filtered = [c for c in self._candles if c.ticker == ticker.upper()]
        if not filtered:
            return None
        sorted_candles = sorted(filtered, key=lambda c: c.date)
        return (sorted_candles[0].date, sorted_candles[-1].date)


# --- Tests ---


class TestComputeRSIUseCase:
    """Test ComputeRSI use case behavior."""

    def test_compute_rsi_with_sufficient_data(self):
        """Should compute RSI when sufficient data available."""
        candles = make_varying_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="BBCA", period=14, days=50)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"
        assert response.period == 14
        assert response.has_values
        assert response.rsi_count > 0

    def test_compute_rsi_with_insufficient_data(self):
        """Should return empty when insufficient data."""
        # 10 candles, but need 15 for period=14
        candles = make_varying_candles("BBCA", 10)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="BBCA", period=14, days=100)

        response = use_case.execute(request)

        assert response.candle_count == 10
        assert response.rsi_count == 0
        assert not response.has_values

    def test_compute_rsi_with_no_cached_data(self):
        """Should return empty response when no cached data."""
        repository = MockRepository([])

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="XXXX", period=14)

        response = use_case.execute(request)

        assert response.candle_count == 0
        assert response.rsi_count == 0
        assert response.date_range is None

    def test_normalizes_ticker_to_uppercase(self):
        """Should normalize ticker to uppercase."""
        candles = make_varying_candles("BBCA", 60)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="bbca", period=14)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"

    def test_empty_ticker_raises_error(self):
        """Should raise ValueError for empty ticker."""
        repository = MockRepository()
        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="", period=14)

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_whitespace_ticker_raises_error(self):
        """Should raise ValueError for whitespace-only ticker."""
        repository = MockRepository()
        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="   ", period=14)

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_invalid_period_raises_error(self):
        """Should raise ValueError for invalid period."""
        repository = MockRepository()
        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="BBCA", period=0)

        with pytest.raises(ValueError, match="Period must be at least 1"):
            use_case.execute(request)

    def test_response_includes_metadata(self):
        """Response should include all metadata."""
        candles = make_varying_candles("BBCA", 60)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="BBCA", period=7, days=30)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"
        assert response.period == 7

    def test_rsi_values_are_tuples_of_date_and_decimal(self):
        """RSI values should be tuples of (date, Decimal)."""
        candles = make_varying_candles("BBCA", 60)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="BBCA", period=7)

        response = use_case.execute(request)

        assert response.has_values
        for date_val, rsi_val in response.values:
            assert isinstance(date_val, date)
            assert isinstance(rsi_val, Decimal)

    def test_rsi_values_bounded_0_to_100(self):
        """All RSI values should be between 0 and 100."""
        candles = make_varying_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="BBCA", period=14)

        response = use_case.execute(request)

        for _, rsi_val in response.values:
            assert Decimal("0") <= rsi_val <= Decimal("100")


class TestComputeRSIWarmUpBuffer:
    """Test warm-up buffer handling in ComputeRSI use case."""

    def test_warm_up_buffer_is_sliced_off(self):
        """RSI values from warm-up period should not be returned."""
        # Create 100 days of data
        candles = make_varying_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        # Request 30 days with period 10 (warm-up = 30 days)
        request = ComputeRSIRequest(ticker="BBCA", period=10, days=30)

        response = use_case.execute(request)

        # All returned values should be within the requested date range
        cutoff = date.today() - timedelta(days=30)
        for date_val, _ in response.values:
            assert date_val >= cutoff

    def test_over_fetch_includes_warm_up_region(self):
        """Use case should fetch extra candles for warm-up."""
        # period=10, days=30, warm_up=30, so need 30+30=60 days minimum
        candles = make_varying_candles("BBCA", 60)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="BBCA", period=10, days=30)

        response = use_case.execute(request)

        # Should have fetched all candles (60)
        assert response.candle_count == 60

    def test_warm_up_multiplier_is_3x_period(self):
        """Warm-up buffer should be 3× period for RSI."""
        assert ComputeRSIUseCase.WARM_UP_MULTIPLIER == 3

    def test_returned_date_range_excludes_warm_up(self):
        """Date range in response should exclude warm-up region."""
        candles = make_varying_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = ComputeRSIUseCase(repository)
        request = ComputeRSIRequest(ticker="BBCA", period=10, days=30)

        response = use_case.execute(request)

        if response.date_range:
            start, end = response.date_range
            cutoff = date.today() - timedelta(days=30)
            # Start date should be >= cutoff (within requested window)
            assert start >= cutoff


class TestComputeRSIResponseDTO:
    """Test ComputeRSIResponse DTO behavior."""

    def test_has_values_property_true_when_values_exist(self):
        """has_values should return True when values exist."""
        response = ComputeRSIResponse(
            ticker="BBCA",
            period=14,
            values=[(date.today(), Decimal("50.00"))],
            candle_count=50,
            rsi_count=36,
            date_range=(date.today(), date.today()),
        )

        assert response.has_values is True

    def test_has_values_property_false_when_empty(self):
        """has_values should return False when no values."""
        response = ComputeRSIResponse(
            ticker="BBCA",
            period=14,
            values=[],
            candle_count=10,
            rsi_count=0,
            date_range=None,
        )

        assert response.has_values is False

    def test_default_period_is_14(self):
        """Default RSI period should be 14."""
        request = ComputeRSIRequest(ticker="BBCA")
        assert request.period == 14

    def test_default_days_is_365(self):
        """Default days should be 365."""
        request = ComputeRSIRequest(ticker="BBCA")
        assert request.days == 365
