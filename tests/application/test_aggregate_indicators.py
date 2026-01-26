"""
Tests for AggregateIndicators use case.

These tests use mock repository to verify:
- Orchestration of SMA, EMA, RSI calculations
- Date alignment (intersection)
- Request/response DTOs
- Error handling
- Edge cases

All tests run offline with no external dependencies.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.use_case.aggregate_indicators import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsResponse,
    AggregateIndicatorsUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot

# --- Test Fixtures ---


def make_candle(ticker: str, days_ago: int, price: str = "100.00") -> Candle:
    """Create a test candle with consistent prices."""
    return Candle(
        ticker=ticker,
        date=date.today() - timedelta(days=days_ago),
        open=Decimal(price),
        high=Decimal(price),
        low=Decimal(price),
        close=Decimal(price),
        volume=100000,
    )


def make_trending_candles(
    ticker: str, count: int, start_price: float = 100.0, trend: float = 1.0
) -> list[Candle]:
    """Create candles with a price trend for realistic indicator testing."""
    candles = []
    for i in range(count - 1, -1, -1):
        price = Decimal(str(start_price + (count - 1 - i) * trend))
        candles.append(
            Candle(
                ticker=ticker,
                date=date.today() - timedelta(days=i),
                open=price,
                high=price + Decimal("1"),
                low=price - Decimal("1"),
                close=price,
                volume=100000,
            )
        )
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


class TestAggregateIndicatorsUseCase:
    """Test AggregateIndicators use case behavior."""

    def test_aggregate_indicators_with_sufficient_data(self):
        """Should compute all indicators when sufficient data available."""
        # Create enough candles for RSI (needs most data due to warm-up)
        # RSI(14) needs 14 periods + warm-up, SMA/EMA(20) need 20 periods
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(
            ticker="BBCA",
            sma_period=20,
            ema_period=20,
            rsi_period=14,
            days=365,
        )

        response = use_case.execute(request)

        assert response.ticker == "BBCA"
        assert response.sma_period == 20
        assert response.ema_period == 20
        assert response.rsi_period == 14
        assert response.has_values
        assert response.snapshot_count > 0
        assert len(response.snapshots) == response.snapshot_count

    def test_snapshots_contain_all_indicators(self):
        """Each snapshot should have SMA, EMA, and RSI values."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="BBCA")

        response = use_case.execute(request)

        assert response.has_values
        for snapshot in response.snapshots:
            assert isinstance(snapshot, IndicatorSnapshot)
            assert isinstance(snapshot.date, date)
            assert isinstance(snapshot.sma, Decimal)
            assert isinstance(snapshot.ema, Decimal)
            assert isinstance(snapshot.rsi, Decimal)

    def test_snapshots_are_sorted_by_date(self):
        """Snapshots should be in chronological order."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="BBCA")

        response = use_case.execute(request)

        assert response.has_values
        dates = [s.date for s in response.snapshots]
        assert dates == sorted(dates)

    def test_date_alignment_intersection(self):
        """Snapshots should only include dates where ALL indicators exist."""
        # With smaller dataset, there will be fewer aligned dates
        # because RSI starts later than SMA/EMA
        candles = make_trending_candles("BBCA", 50)
        repository = MockRepository(candles)

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(
            ticker="BBCA",
            sma_period=10,
            ema_period=10,
            rsi_period=14,
            days=365,
        )

        response = use_case.execute(request)

        # All snapshots should have all three indicators
        for snapshot in response.snapshots:
            assert snapshot.sma is not None
            assert snapshot.ema is not None
            assert snapshot.rsi is not None

    def test_with_no_cached_data(self):
        """Should return empty response when no cached data."""
        repository = MockRepository([])

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="XXXX")

        response = use_case.execute(request)

        assert response.candle_count == 0
        assert response.snapshot_count == 0
        assert not response.has_values
        assert response.date_range is None

    def test_with_insufficient_data(self):
        """Should return empty snapshots when insufficient data for indicators."""
        # Only 5 candles - not enough for any indicator with default periods
        candles = [make_candle("BBCA", i) for i in range(4, -1, -1)]
        repository = MockRepository(candles)

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(
            ticker="BBCA",
            sma_period=20,
            ema_period=20,
            rsi_period=14,
        )

        response = use_case.execute(request)

        assert response.snapshot_count == 0
        assert not response.has_values

    def test_normalizes_ticker_to_uppercase(self):
        """Should normalize ticker to uppercase."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="bbca")

        response = use_case.execute(request)

        assert response.ticker == "BBCA"

    def test_empty_ticker_raises_error(self):
        """Should raise ValueError for empty ticker."""
        repository = MockRepository()
        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="")

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_whitespace_ticker_raises_error(self):
        """Should raise ValueError for whitespace-only ticker."""
        repository = MockRepository()
        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="   ")

        with pytest.raises(ValueError, match="Ticker cannot be empty"):
            use_case.execute(request)

    def test_invalid_sma_period_raises_error(self):
        """Should raise ValueError for invalid SMA period."""
        repository = MockRepository()
        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="BBCA", sma_period=0)

        with pytest.raises(ValueError, match="SMA period must be at least 1"):
            use_case.execute(request)

    def test_invalid_ema_period_raises_error(self):
        """Should raise ValueError for invalid EMA period."""
        repository = MockRepository()
        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="BBCA", ema_period=0)

        with pytest.raises(ValueError, match="EMA period must be at least 1"):
            use_case.execute(request)

    def test_invalid_rsi_period_raises_error(self):
        """Should raise ValueError for invalid RSI period."""
        repository = MockRepository()
        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="BBCA", rsi_period=0)

        with pytest.raises(ValueError, match="RSI period must be at least 1"):
            use_case.execute(request)

    def test_custom_periods(self):
        """Should respect custom indicator periods."""
        candles = make_trending_candles("BBCA", 200)
        repository = MockRepository(candles)

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(
            ticker="BBCA",
            sma_period=50,
            ema_period=50,
            rsi_period=7,
        )

        response = use_case.execute(request)

        assert response.sma_period == 50
        assert response.ema_period == 50
        assert response.rsi_period == 7
        assert response.has_values

    def test_response_date_range_matches_snapshots(self):
        """Response date range should match first and last snapshot dates."""
        candles = make_trending_candles("BBCA", 100)
        repository = MockRepository(candles)

        use_case = AggregateIndicatorsUseCase(repository)
        request = AggregateIndicatorsRequest(ticker="BBCA")

        response = use_case.execute(request)

        assert response.has_values
        assert response.date_range is not None
        assert response.date_range[0] == response.snapshots[0].date
        assert response.date_range[1] == response.snapshots[-1].date


class TestAggregateIndicatorsResponseDTO:
    """Test AggregateIndicatorsResponse DTO behavior."""

    def test_has_values_property_true_when_snapshots_exist(self):
        """has_values should return True when snapshots exist."""
        response = AggregateIndicatorsResponse(
            ticker="BBCA",
            sma_period=20,
            ema_period=20,
            rsi_period=14,
            snapshots=[
                IndicatorSnapshot(
                    date=date.today(),
                    sma=Decimal("100"),
                    ema=Decimal("100"),
                    rsi=Decimal("50"),
                )
            ],
            candle_count=100,
            snapshot_count=1,
            date_range=(date.today(), date.today()),
        )

        assert response.has_values is True

    def test_has_values_property_false_when_empty(self):
        """has_values should return False when no snapshots."""
        response = AggregateIndicatorsResponse(
            ticker="BBCA",
            sma_period=20,
            ema_period=20,
            rsi_period=14,
            snapshots=[],
            candle_count=10,
            snapshot_count=0,
            date_range=None,
        )

        assert response.has_values is False


class TestAggregateIndicatorsRequestDTO:
    """Test AggregateIndicatorsRequest DTO defaults."""

    def test_default_periods(self):
        """Request should have industry-standard default periods."""
        request = AggregateIndicatorsRequest(ticker="BBCA")

        assert request.sma_period == 20
        assert request.ema_period == 20
        assert request.rsi_period == 14
        assert request.days == 365

    def test_custom_values_override_defaults(self):
        """Custom values should override defaults."""
        request = AggregateIndicatorsRequest(
            ticker="BBCA",
            sma_period=50,
            ema_period=100,
            rsi_period=7,
            days=180,
        )

        assert request.sma_period == 50
        assert request.ema_period == 100
        assert request.rsi_period == 7
        assert request.days == 180
