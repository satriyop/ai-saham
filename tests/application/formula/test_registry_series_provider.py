"""Tests for RegistrySeriesProvider.

Direct tests using a fake registry and candles.
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.formula.registry_series_provider import (
    RegistrySeriesProvider,
)
from src.domain.entities.candle import Candle


def make_candle(
    day_offset: int,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: int = 10000,
) -> Candle:
    """Helper to create a test candle."""
    return Candle(
        ticker="TEST",
        date=date(2024, 1, 1) + timedelta(days=day_offset),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


class FakeRegistry:
    """Minimal fake indicator registry for testing."""

    def __init__(self) -> None:
        self._default_periods: dict[str, int] = {"SMA": 20, "EMA": 20, "RSI": 14}
        self._results: dict[tuple[str, int], list[tuple[date, Decimal]]] = {}

    def get_default_period(self, name: str) -> int:
        return self._default_periods.get(name, 14)

    def compute(self, name: str, candles: list[Candle], period: int) -> list[tuple[date, Decimal]]:
        key = (name, period)
        if key in self._results:
            return self._results[key]
        # Compute fake RSI-like values
        return [(c.date, Decimal("50.0")) for c in candles]


class TestGetSeries:
    """Tests for get_series method."""

    def test_get_close(self) -> None:
        candles = [make_candle(i, close=float(100 + i)) for i in range(3)]
        provider = RegistrySeriesProvider(FakeRegistry(), candles)
        result = provider.get_series("CLOSE")
        assert result == [Decimal("100"), Decimal("101"), Decimal("102")]

    def test_get_open(self) -> None:
        candles = [make_candle(i, open_=float(200 + i)) for i in range(3)]
        provider = RegistrySeriesProvider(FakeRegistry(), candles)
        result = provider.get_series("OPEN")
        assert result == [Decimal("200"), Decimal("201"), Decimal("202")]

    def test_get_high(self) -> None:
        candles = [make_candle(i, high=float(300 + i)) for i in range(3)]
        provider = RegistrySeriesProvider(FakeRegistry(), candles)
        result = provider.get_series("HIGH")
        assert result == [Decimal("300"), Decimal("301"), Decimal("302")]

    def test_get_low(self) -> None:
        candles = [make_candle(i, low=float(400 + i), high=float(400 + i + 2)) for i in range(3)]
        provider = RegistrySeriesProvider(FakeRegistry(), candles)
        result = provider.get_series("LOW")
        assert result == [Decimal("400"), Decimal("401"), Decimal("402")]

    def test_get_volume(self) -> None:
        candles = [make_candle(i, volume=1000 * (i + 1)) for i in range(3)]
        provider = RegistrySeriesProvider(FakeRegistry(), candles)
        result = provider.get_series("VOLUME")
        assert result == [Decimal("1000"), Decimal("2000"), Decimal("3000")]

    def test_get_indicator_series(self) -> None:
        """Indicator series strips dates."""
        candles = [make_candle(i) for i in range(3)]
        provider = RegistrySeriesProvider(FakeRegistry(), candles)
        result = provider.get_series("RSI")
        assert result == [Decimal("50.0"), Decimal("50.0"), Decimal("50.0")]


class TestComputeIndicator:
    """Tests for compute_indicator method."""

    def test_compute_indicator_strips_dates(self) -> None:
        """compute_indicator returns values without dates."""
        candles = [make_candle(i) for i in range(5)]
        provider = RegistrySeriesProvider(FakeRegistry(), candles)
        result = provider.compute_indicator("SMA", 20)
        assert len(result) == 5
        assert all(isinstance(v, Decimal) for v in result)
        assert all(v == Decimal("50.0") for v in result)


class TestGetDefaultPeriod:
    """Tests for get_default_period method."""

    def test_get_default_period(self) -> None:
        candles = [make_candle(0)]
        provider = RegistrySeriesProvider(FakeRegistry(), candles)
        assert provider.get_default_period("RSI") == 14
        assert provider.get_default_period("SMA") == 20
