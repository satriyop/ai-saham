"""
Tests for Donchian Channel indicator plugins:
  DonchianUpperIndicator, DonchianLowerIndicator, DonchianMiddleIndicator
"""

from datetime import date, timedelta
from decimal import Decimal

from plugins.indicators.donchian_channel import (
    DonchianLowerIndicator,
    DonchianMiddleIndicator,
    DonchianUpperIndicator,
)
from src.application.services.bootstrap import create_indicator_registry
from src.domain.entities.candle import Candle


def make_candle(i: int, close: float, high: float, low: float) -> Candle:
    return Candle(
        ticker="TEST",
        date=date(2025, 1, 1) + timedelta(days=i),
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=100_000,
    )


class TestDonchianChannelIndicators:
    def test_output_length(self):
        # We need period + 1 candles to produce 1 value
        # 30 candles, period 20 -> length of values should be 10 (30 - 20)
        candles = [make_candle(i, 1000, 1010, 990) for i in range(30)]
        
        upper = DonchianUpperIndicator().compute(candles, 20)
        lower = DonchianLowerIndicator().compute(candles, 20)
        mid = DonchianMiddleIndicator().compute(candles, 20)
        
        assert len(upper) == 10
        assert len(lower) == 10
        assert len(mid) == 10

    def test_upper_and_lower_calculations(self):
        # Create candles with a specific high and low pattern
        # Lookback window for candle 5 (period=5) will look at candles 0 to 4.
        candles = [
            make_candle(0, 100, 105, 95), # high=105, low=95
            make_candle(1, 101, 110, 96), # high=110, low=96
            make_candle(2, 102, 108, 92), # high=108, low=92 (min low)
            make_candle(3, 103, 115, 98), # high=115, low=98 (max high)
            make_candle(4, 104, 107, 97), # high=107, low=97
            make_candle(5, 105, 120, 85), # high=120, low=85 (ignored for index 5 calculation)
        ]
        
        upper = DonchianUpperIndicator().compute(candles, 5)
        lower = DonchianLowerIndicator().compute(candles, 5)
        mid = DonchianMiddleIndicator().compute(candles, 5)
        
        # We have 6 candles, period 5 -> exactly 1 output value representing index 5's channel
        assert len(upper) == 1
        assert len(lower) == 1
        assert len(mid) == 1
        
        assert upper[0] == Decimal("115") # max(105, 110, 108, 115, 107)
        assert lower[0] == Decimal("92")  # min(95, 96, 92, 98, 97)
        assert mid[0] == Decimal("103.5") # (115 + 92) / 2

    def test_too_few_candles_returns_empty(self):
        # For period 20, 20 candles returns empty list (we need at least 21 to have 1 lookup date)
        candles = [make_candle(i, 1000, 1010, 990) for i in range(20)]
        assert DonchianUpperIndicator().compute(candles, 20) == []
        assert DonchianLowerIndicator().compute(candles, 20) == []
        assert DonchianMiddleIndicator().compute(candles, 20) == []

    def test_plugin_attributes(self):
        assert DonchianUpperIndicator.name == "DONCHIAN_UPPER"
        assert DonchianUpperIndicator.default_period == 20
        
        assert DonchianLowerIndicator.name == "DONCHIAN_LOWER"
        assert DonchianLowerIndicator.default_period == 20
        
        assert DonchianMiddleIndicator.name == "DONCHIAN_MIDDLE"
        assert DonchianMiddleIndicator.default_period == 20


class TestDonchianRegistryIntegration:
    def test_all_discovered(self):
        registry = create_indicator_registry("plugins/indicators")
        for name in ("DONCHIAN_UPPER", "DONCHIAN_LOWER", "DONCHIAN_MIDDLE"):
            assert registry.is_registered(name), f"{name} not registered"

    def test_registry_compute_aligns_dates(self):
        registry = create_indicator_registry("plugins/indicators")
        candles = [make_candle(i, 100, 105, 95) for i in range(25)]
        
        result = registry.compute("DONCHIAN_UPPER", candles, 20)
        assert len(result) == 5
        # The last value's date should match the last candle's date
        assert result[-1][0] == candles[-1].date
        assert isinstance(result[-1][1], Decimal)
