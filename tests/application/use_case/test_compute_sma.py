"""
Tests for ComputeSMA use case.

These tests use mock repository to verify:
- Orchestration between repository and indicator
- Request/response DTOs
- Error handling
- Edge cases

All tests run offline with no external dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.use_case.compute_sma_use_case import (
    ComputeSMARequest,
    ComputeSMAResponse,
    ComputeSMAUseCase,
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


class TestComputeSMAUseCase:
    """Test ComputeSMA use case behavior."""

    def test_compute_sma_with_sufficient_data(self):
        """Should compute SMA when sufficient data available."""
        candles = [make_candle("BBCA", i, f"{100 + i}.00") for i in range(49, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="BBCA", period=20, days=100)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"
        assert response.period == 20
        assert response.candle_count == 50
        assert response.sma_count == 31  # 50 - 20 + 1
        assert response.has_values

    def test_compute_sma_with_insufficient_data(self):
        """Should return empty when insufficient data."""
        candles = [make_candle("BBCA", i) for i in range(9, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="BBCA", period=20, days=100)

        response = use_case.execute(request)

        assert response.candle_count == 10
        assert response.sma_count == 0
        assert not response.has_values

    def test_compute_sma_with_no_cached_data(self):
        """Should return empty response when no cached data."""
        repository = MockRepository([])

        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="XXXX", period=20)

        response = use_case.execute(request)

        assert response.candle_count == 0
        assert response.sma_count == 0
        assert response.date_range is None

    def test_normalizes_ticker_to_uppercase(self):
        """Should normalize ticker to uppercase."""
        candles = [make_candle("BBCA", i) for i in range(29, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="bbca", period=20)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"

    def test_empty_ticker_raises_error(self):
        """Should raise ValueError for empty ticker."""
        repository = MockRepository()
        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="", period=20)

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_whitespace_ticker_raises_error(self):
        """Should raise ValueError for whitespace-only ticker."""
        repository = MockRepository()
        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="   ", period=20)

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_invalid_period_raises_error(self):
        """Should raise ValueError for invalid period."""
        repository = MockRepository()
        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="BBCA", period=0)

        with pytest.raises(ValueError, match="Period must be at least 1"):
            use_case.execute(request)

    def test_response_includes_metadata(self):
        """Response should include all metadata."""
        candles = [make_candle("BBCA", i) for i in range(29, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="BBCA", period=10, price_field="high", days=100)

        response = use_case.execute(request)

        assert response.ticker == "BBCA"
        assert response.period == 10
        assert response.price_field == "high"
        assert response.date_range is not None

    def test_response_date_range_matches_candles(self):
        """Response date range should match actual candle dates."""
        candles = [make_candle("BBCA", i) for i in range(29, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="BBCA", period=10)

        response = use_case.execute(request)

        assert response.date_range is not None
        sorted_candles = sorted(candles, key=lambda c: c.date)
        assert response.date_range[0] == sorted_candles[0].date
        assert response.date_range[1] == sorted_candles[-1].date

    def test_sma_values_are_tuples_of_date_and_decimal(self):
        """SMA values should be tuples of (date, Decimal)."""
        candles = [make_candle("BBCA", i) for i in range(29, -1, -1)]
        repository = MockRepository(candles)

        use_case = ComputeSMAUseCase(repository)
        request = ComputeSMARequest(ticker="BBCA", period=10)

        response = use_case.execute(request)

        assert response.has_values
        for date_val, sma_val in response.values:
            assert isinstance(date_val, date)
            assert isinstance(sma_val, Decimal)


class TestComputeSMAResponseDTO:
    """Test ComputeSMAResponse DTO behavior."""

    def test_has_values_property_true_when_values_exist(self):
        """has_values should return True when values exist."""
        response = ComputeSMAResponse(
            ticker="BBCA",
            period=20,
            price_field="close",
            values=[(date.today(), Decimal("100.00"))],
            candle_count=50,
            sma_count=31,
            date_range=(date.today(), date.today()),
        )

        assert response.has_values is True

    def test_has_values_property_false_when_empty(self):
        """has_values should return False when no values."""
        response = ComputeSMAResponse(
            ticker="BBCA",
            period=20,
            price_field="close",
            values=[],
            candle_count=10,
            sma_count=0,
            date_range=None,
        )

        assert response.has_values is False
