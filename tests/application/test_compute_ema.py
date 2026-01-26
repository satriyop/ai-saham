"""
Tests for ComputeEMA use case.

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

from src.application.use_case.compute_ema import (
    ComputeEMARequest,
    ComputeEMAResponse,
    ComputeEMAUseCase,
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


class TestComputeEMAUseCase:
    """Test ComputeEMA use case behavior."""

    def test_compute_ema_with_sufficient_data(self):
        """Should compute EMA when sufficient data available."""
        candles = [make_candle("BBCA", i, f"{100 + i}.00") for i in range(99, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="BBCA", period=20, days=50)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"
        assert response.period == 20
        assert response.has_values
        # EMA values should exist
        assert response.ema_count > 0

    def test_compute_ema_with_insufficient_data(self):
        """Should return empty when insufficient data."""
        candles = [make_candle("BBCA", i) for i in range(9, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="BBCA", period=20, days=100)

        response = use_case.execute(request)

        assert response.candle_count == 10
        assert response.ema_count == 0
        assert not response.has_values

    def test_compute_ema_with_no_cached_data(self):
        """Should return empty response when no cached data."""
        repository = MockRepository([])

        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="XXXX", period=20)

        response = use_case.execute(request)

        assert response.candle_count == 0
        assert response.ema_count == 0
        assert response.date_range is None

    def test_normalizes_ticker_to_uppercase(self):
        """Should normalize ticker to uppercase."""
        candles = [make_candle("BBCA", i) for i in range(59, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="bbca", period=20)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"

    def test_empty_ticker_raises_error(self):
        """Should raise ValueError for empty ticker."""
        repository = MockRepository()
        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="", period=20)

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_whitespace_ticker_raises_error(self):
        """Should raise ValueError for whitespace-only ticker."""
        repository = MockRepository()
        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="   ", period=20)

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_invalid_period_raises_error(self):
        """Should raise ValueError for invalid period."""
        repository = MockRepository()
        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="BBCA", period=0)

        with pytest.raises(ValueError, match="Period must be at least 1"):
            use_case.execute(request)

    def test_response_includes_metadata(self):
        """Response should include all metadata."""
        candles = [make_candle("BBCA", i) for i in range(59, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(
            ticker="BBCA", period=10, price_field="high", days=30
        )

        response = use_case.execute(request)

        assert response.ticker == "BBCA"
        assert response.period == 10
        assert response.price_field == "high"

    def test_ema_values_are_tuples_of_date_and_decimal(self):
        """EMA values should be tuples of (date, Decimal)."""
        candles = [make_candle("BBCA", i) for i in range(59, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="BBCA", period=10)

        response = use_case.execute(request)

        assert response.has_values
        for date_val, ema_val in response.values:
            assert isinstance(date_val, date)
            assert isinstance(ema_val, Decimal)


class TestComputeEMAWarmUpBuffer:
    """Test warm-up buffer handling in ComputeEMA use case."""

    def test_warm_up_buffer_is_sliced_off(self):
        """EMA values from warm-up period should not be returned."""
        # Create 100 days of data
        candles = [make_candle("BBCA", i) for i in range(99, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeEMAUseCase(repository)
        # Request 30 days with period 10 (warm-up = 20 days)
        request = ComputeEMARequest(ticker="BBCA", period=10, days=30)

        response = use_case.execute(request)

        # All returned values should be within the requested date range
        cutoff = date.today() - timedelta(days=30)
        for date_val, _ in response.values:
            assert date_val >= cutoff

    def test_over_fetch_includes_warm_up_region(self):
        """Use case should fetch extra candles for warm-up."""
        # Create exactly enough candles for warm-up + requested days
        # period=10, days=30, warm_up=20, so need 30+20=50 days minimum
        candles = [make_candle("BBCA", i) for i in range(49, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="BBCA", period=10, days=30)

        response = use_case.execute(request)

        # Should have fetched all candles (50)
        assert response.candle_count == 50
        # Returned values should be within the ~30 day window
        # Note: "days=30" means dates from (today - 30 days) to today (inclusive)
        # which can yield 31 values depending on date alignment
        assert response.ema_count <= 32  # Allow for boundary conditions

    def test_warm_up_multiplier_is_2x_period(self):
        """Warm-up buffer should be 2× period."""
        assert ComputeEMAUseCase.WARM_UP_MULTIPLIER == 2

    def test_returned_date_range_excludes_warm_up(self):
        """Date range in response should exclude warm-up region."""
        candles = [make_candle("BBCA", i) for i in range(99, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeEMAUseCase(repository)
        request = ComputeEMARequest(ticker="BBCA", period=10, days=30)

        response = use_case.execute(request)

        if response.date_range:
            start, end = response.date_range
            cutoff = date.today() - timedelta(days=30)
            # Start date should be >= cutoff (within requested window)
            assert start >= cutoff


class TestComputeEMAResponseDTO:
    """Test ComputeEMAResponse DTO behavior."""

    def test_has_values_property_true_when_values_exist(self):
        """has_values should return True when values exist."""
        response = ComputeEMAResponse(
            ticker="BBCA",
            period=20,
            price_field="close",
            values=[(date.today(), Decimal("100.00"))],
            candle_count=50,
            ema_count=31,
            date_range=(date.today(), date.today()),
        )

        assert response.has_values is True

    def test_has_values_property_false_when_empty(self):
        """has_values should return False when no values."""
        response = ComputeEMAResponse(
            ticker="BBCA",
            period=20,
            price_field="close",
            values=[],
            candle_count=10,
            ema_count=0,
            date_range=None,
        )

        assert response.has_values is False
