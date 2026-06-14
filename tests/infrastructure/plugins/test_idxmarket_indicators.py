"""
Tests for IDX-market-specific indicator plugins:
  VolumeRatioIndicator, MoneyFlowIndexIndicator,
  OnBalanceVolumeIndicator, WilliamsRIndicator,
  RelativeStrengthIHSGIndicator
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from plugins.indicators.mfi import MoneyFlowIndexIndicator
from plugins.indicators.obv import OnBalanceVolumeIndicator
from plugins.indicators.relative_strength import RelativeStrengthIHSGIndicator
from plugins.indicators.volume_ratio import VolumeRatioIndicator
from plugins.indicators.williams_r import WilliamsRIndicator
from src.application.services.bootstrap import create_indicator_registry
from src.domain.entities.candle import Candle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_candle(i: int, close: float, volume: int = 100_000,
                high: float | None = None, low: float | None = None) -> Candle:
    p = Decimal(str(close))
    return Candle(
        ticker="TEST",
        date=date(2025, 1, 1) + timedelta(days=i),
        open=p,
        high=Decimal(str(high)) if high else p + Decimal("10"),
        low=Decimal(str(low)) if low else p - Decimal("5"),
        close=p,
        volume=volume,
    )


def rising_candles(n: int, base: float = 1000.0, step: float = 5.0) -> list[Candle]:
    return [make_candle(i, base + i * step) for i in range(n)]


def flat_candles(n: int, price: float = 1000.0) -> list[Candle]:
    return [make_candle(i, price) for i in range(n)]


# ---------------------------------------------------------------------------
# VolumeRatioIndicator
# ---------------------------------------------------------------------------

class TestVolumeRatioIndicator:
    def test_output_length(self):
        candles = [make_candle(i, 1000, volume=100_000) for i in range(30)]
        result = VolumeRatioIndicator().compute(candles, 20)
        assert len(result) == 10  # 30 - 20

    def test_vr_above_one_when_volume_spikes(self):
        candles = [make_candle(i, 1000, volume=100_000) for i in range(21)]
        candles[20] = make_candle(20, 1000, volume=300_000)
        result = VolumeRatioIndicator().compute(candles, 20)
        assert result[-1] == Decimal("3.00")

    def test_vr_below_one_when_volume_thin(self):
        candles = [make_candle(i, 1000, volume=100_000) for i in range(21)]
        candles[20] = make_candle(20, 1000, volume=50_000)
        result = VolumeRatioIndicator().compute(candles, 20)
        assert result[-1] == Decimal("0.50")

    def test_vr_one_when_volume_constant(self):
        candles = [make_candle(i, 1000, volume=100_000) for i in range(25)]
        result = VolumeRatioIndicator().compute(candles, 20)
        for v in result:
            assert v == Decimal("1.00")

    def test_too_few_candles_returns_empty(self):
        candles = [make_candle(i, 1000) for i in range(20)]
        assert VolumeRatioIndicator().compute(candles, 20) == []

    def test_plugin_attributes(self):
        assert VolumeRatioIndicator.name == "VOLUME_RATIO"
        assert VolumeRatioIndicator.default_period == 20


# ---------------------------------------------------------------------------
# MoneyFlowIndexIndicator
# ---------------------------------------------------------------------------

class TestMoneyFlowIndexIndicator:
    def test_output_length(self):
        candles = rising_candles(30)
        result = MoneyFlowIndexIndicator().compute(candles, 14)
        assert len(result) == 30 - 14

    def test_range_0_to_100(self):
        candles = rising_candles(50)
        result = MoneyFlowIndexIndicator().compute(candles, 14)
        for v in result:
            assert Decimal("0") <= v <= Decimal("100")

    def test_high_mfi_on_consistent_up_days(self):
        # All up days → positive money flow dominates → MFI near 100
        candles = rising_candles(30)
        result = MoneyFlowIndexIndicator().compute(candles, 14)
        assert result[-1] > Decimal("70")

    def test_mfi_50_on_alternating_days(self):
        # Alternating up/down with equal volume → MFI near 50
        prices = [1000, 1010, 1000, 1010, 1000, 1010, 1000, 1010,
                  1000, 1010, 1000, 1010, 1000, 1010, 1000]
        candles = [make_candle(i, p) for i, p in enumerate(prices)]
        result = MoneyFlowIndexIndicator().compute(candles, 14)
        assert len(result) == 1
        assert Decimal("40") < result[0] < Decimal("60")

    def test_too_few_candles_returns_empty(self):
        candles = rising_candles(14)
        assert MoneyFlowIndexIndicator().compute(candles, 14) == []

    def test_plugin_attributes(self):
        assert MoneyFlowIndexIndicator.name == "MFI"
        assert MoneyFlowIndexIndicator.default_period == 14


# ---------------------------------------------------------------------------
# OnBalanceVolumeIndicator
# ---------------------------------------------------------------------------

class TestOnBalanceVolumeIndicator:
    def test_output_length_equals_candles(self):
        candles = rising_candles(30)
        result = OnBalanceVolumeIndicator().compute(candles, 1)
        assert len(result) == 30

    def test_obv_increases_on_up_day(self):
        candles = [
            make_candle(0, 1000, volume=100_000),
            make_candle(1, 1010, volume=200_000),
        ]
        result = OnBalanceVolumeIndicator().compute(candles, 1)
        assert result[1] == Decimal("300000")  # 100k + 200k

    def test_obv_decreases_on_down_day(self):
        candles = [
            make_candle(0, 1000, volume=100_000),
            make_candle(1, 990, volume=200_000),
        ]
        result = OnBalanceVolumeIndicator().compute(candles, 1)
        assert result[1] == Decimal("-100000")  # 100k - 200k

    def test_obv_unchanged_on_flat_day(self):
        candles = [
            make_candle(0, 1000, volume=100_000),
            make_candle(1, 1000, volume=200_000),
        ]
        result = OnBalanceVolumeIndicator().compute(candles, 1)
        assert result[1] == result[0]

    def test_obv_rising_on_consistent_up_days(self):
        candles = rising_candles(10)
        result = OnBalanceVolumeIndicator().compute(candles, 1)
        for i in range(1, len(result)):
            assert result[i] > result[i - 1]

    def test_empty_input_returns_empty(self):
        assert OnBalanceVolumeIndicator().compute([], 1) == []

    def test_plugin_attributes(self):
        assert OnBalanceVolumeIndicator.name == "OBV"
        assert OnBalanceVolumeIndicator.default_period == 1


# ---------------------------------------------------------------------------
# WilliamsRIndicator
# ---------------------------------------------------------------------------

class TestWilliamsRIndicator:
    def test_output_length(self):
        candles = rising_candles(30)
        result = WilliamsRIndicator().compute(candles, 14)
        assert len(result) == 30 - 14 + 1  # 17

    def test_range_minus100_to_0(self):
        candles = rising_candles(30)
        result = WilliamsRIndicator().compute(candles, 14)
        for v in result:
            assert Decimal("-100") <= v <= Decimal("0")

    def test_zero_when_close_at_highest_high(self):
        # Rising candles: close is always at or near the highest point
        candles = [
            make_candle(i, 1000 + i * 10, high=1000 + i * 10, low=990 + i * 10)
            for i in range(14)
        ]
        result = WilliamsRIndicator().compute(candles, 14)
        assert result[0] == Decimal("0.00")

    def test_minus100_when_close_at_lowest_low(self):
        # Falling candles: close is always at the lowest point
        candles = [
            make_candle(i, 1000 - i * 10, high=1010 - i * 10, low=1000 - i * 10)
            for i in range(14)
        ]
        result = WilliamsRIndicator().compute(candles, 14)
        assert result[0] == Decimal("-100.00")

    def test_minus50_on_flat_candles(self):
        candles = [make_candle(i, 1000, high=1010, low=990) for i in range(14)]
        result = WilliamsRIndicator().compute(candles, 14)
        assert result[0] == Decimal("-50.00")

    def test_too_few_candles_returns_empty(self):
        candles = rising_candles(13)
        assert WilliamsRIndicator().compute(candles, 14) == []

    def test_plugin_attributes(self):
        assert WilliamsRIndicator.name == "WILLIAMS_R"
        assert WilliamsRIndicator.default_period == 14


# ---------------------------------------------------------------------------
# RelativeStrengthIHSGIndicator
# ---------------------------------------------------------------------------

class TestRelativeStrengthIHSGIndicator:
    def _make_ihsg(self, n: int, base: float = 7000.0, step: float = 10.0) -> list[Candle]:
        return [
            Candle(
                ticker="^JKSE",
                date=date(2025, 1, 1) + timedelta(days=i),
                open=Decimal(str(base + i * step)),
                high=Decimal(str(base + i * step + 5)),
                low=Decimal(str(base + i * step - 5)),
                close=Decimal(str(base + i * step)),
                volume=1_000_000_000,
            )
            for i in range(n)
        ]

    def test_output_length(self):
        candles = rising_candles(30)
        ihsg = self._make_ihsg(30)
        plugin = RelativeStrengthIHSGIndicator()
        plugin.set_index_candles(ihsg)
        result = plugin.compute(candles, 20)
        assert len(result) == 10  # 30 - 20

    def test_rs_above_one_when_stock_outperforms(self):
        # Stock: +20% over 20 days, IHSG: +10% — RS should be 2.0
        stock = [make_candle(i, 1000 + i * 10, volume=100_000) for i in range(21)]
        ihsg = [
            Candle(ticker="^JKSE",
                   date=date(2025, 1, 1) + timedelta(days=i),
                   open=Decimal(str(7000 + i * 5)),
                   high=Decimal(str(7000 + i * 5 + 5)),
                   low=Decimal(str(7000 + i * 5 - 5)),
                   close=Decimal(str(7000 + i * 5)),
                   volume=1_000_000_000)
            for i in range(21)
        ]
        plugin = RelativeStrengthIHSGIndicator()
        plugin.set_index_candles(ihsg)
        result = plugin.compute(stock, 20)
        assert len(result) == 1
        # stock return = (1200-1000)/1000 = 0.20; ihsg return = (7100-7000)/7000 ≈ 0.0143
        assert result[0] > Decimal("1")

    def test_rs_below_one_when_stock_underperforms(self):
        # Stock flat, IHSG rises — RS < 1
        stock = [make_candle(i, 1000, volume=100_000) for i in range(21)]
        ihsg = self._make_ihsg(21)
        plugin = RelativeStrengthIHSGIndicator()
        plugin.set_index_candles(ihsg)
        result = plugin.compute(stock, 20)
        assert result[0] < Decimal("1")

    def test_rs_one_when_no_index_data(self):
        candles = rising_candles(25)
        plugin = RelativeStrengthIHSGIndicator()
        # No index data injected
        result = plugin.compute(candles, 20)
        for v in result:
            assert v == Decimal("1")

    def test_too_few_candles_returns_empty(self):
        candles = rising_candles(20)
        ihsg = self._make_ihsg(20)
        plugin = RelativeStrengthIHSGIndicator()
        plugin.set_index_candles(ihsg)
        assert plugin.compute(candles, 20) == []

    def test_plugin_attributes(self):
        assert RelativeStrengthIHSGIndicator.name == "RS_IHSG"
        assert RelativeStrengthIHSGIndicator.default_period == 20


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestIDXIndicatorsRegistryIntegration:
    def test_all_discovered(self):
        registry = create_indicator_registry("plugins/indicators")
        for name in ("VOLUME_RATIO", "MFI", "OBV", "WILLIAMS_R", "RS_IHSG"):
            assert registry.is_registered(name), f"{name} not registered"

    def test_default_periods(self):
        registry = create_indicator_registry("plugins/indicators")
        assert registry.get_default_period("VOLUME_RATIO") == 20
        assert registry.get_default_period("MFI") == 14
        assert registry.get_default_period("OBV") == 1
        assert registry.get_default_period("WILLIAMS_R") == 14
        assert registry.get_default_period("RS_IHSG") == 20

    def test_registry_compute_returns_date_tuples(self):
        registry = create_indicator_registry("plugins/indicators")
        candles = rising_candles(50)
        for name, period in [
            ("VOLUME_RATIO", 20), ("MFI", 14), ("OBV", 1),
            ("WILLIAMS_R", 14), ("RS_IHSG", 20),
        ]:
            result = registry.compute(name, candles, period)
            assert isinstance(result, list), f"{name} did not return a list"
            if result:
                d, v = result[0]
                from datetime import date as date_type
                assert isinstance(d, date_type)
                assert isinstance(v, Decimal)

    def test_volume_ratio_aligns_to_end_of_candles(self):
        registry = create_indicator_registry("plugins/indicators")
        candles = rising_candles(30)
        result = registry.compute("VOLUME_RATIO", candles, 20)
        assert result[-1][0] == candles[-1].date

    def test_obv_aligns_to_all_candles(self):
        registry = create_indicator_registry("plugins/indicators")
        candles = rising_candles(30)
        result = registry.compute("OBV", candles, 1)
        assert len(result) == 30
        assert result[0][0] == candles[0].date
        assert result[-1][0] == candles[-1].date
