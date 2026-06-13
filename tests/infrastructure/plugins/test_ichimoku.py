"""
Tests for the Ichimoku Kinko Hyo indicator plugin.

Covers: correctness of each component, displacement alignment,
minimum-candle edge cases, and registry integration.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from plugins.indicators.ichimoku import (
    IchimokuChikou,
    IchimokuKijun,
    IchimokuSpanA,
    IchimokuSpanB,
    IchimokuTenkan,
)
from src.application.services.bootstrap import create_indicator_registry
from src.domain.entities.candle import Candle


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_candles(n: int, base: int = 1000, step: int = 5) -> list[Candle]:
    """Monotonically rising candles — predictable highs/lows for assertions."""
    candles = []
    for i in range(n):
        p = Decimal(str(base + i * step))
        candles.append(
            Candle(
                ticker="TEST",
                date=date(2025, 1, 1) + timedelta(days=i),
                open=p,
                high=p + 10,
                low=p - 5,
                close=p + 2,
                volume=100_000,
            )
        )
    return candles


def midpoint(candles: list[Candle], start: int, end: int) -> Decimal:
    """(highest high + lowest low) / 2 over candles[start:end]."""
    window = candles[start:end]
    highest = max(c.high for c in window)
    lowest = min(c.low for c in window)
    return (highest + lowest) / Decimal("2")


# ---------------------------------------------------------------------------
# IchimokuTenkan
# ---------------------------------------------------------------------------


class TestIchimokuTenkan:
    def test_output_length(self):
        candles = make_candles(50)
        result = IchimokuTenkan().compute(candles, 9)
        assert len(result) == 50 - 9 + 1  # 42

    def test_first_value(self):
        candles = make_candles(20)
        result = IchimokuTenkan().compute(candles, 9)
        # First result uses candles[0:9]
        assert result[0] == midpoint(candles, 0, 9)

    def test_last_value(self):
        candles = make_candles(20)
        result = IchimokuTenkan().compute(candles, 9)
        # Last result uses candles[11:20]
        assert result[-1] == midpoint(candles, 11, 20)

    def test_too_few_candles_returns_empty(self):
        candles = make_candles(8)
        assert IchimokuTenkan().compute(candles, 9) == []

    def test_exactly_minimum_candles(self):
        candles = make_candles(9)
        result = IchimokuTenkan().compute(candles, 9)
        assert len(result) == 1

    def test_plugin_attributes(self):
        assert IchimokuTenkan.name == "ICHIMOKU_TENKAN"
        assert IchimokuTenkan.default_period == 9


# ---------------------------------------------------------------------------
# IchimokuKijun
# ---------------------------------------------------------------------------


class TestIchimokuKijun:
    def test_output_length(self):
        candles = make_candles(50)
        result = IchimokuKijun().compute(candles, 26)
        assert len(result) == 50 - 26 + 1  # 25

    def test_first_value(self):
        candles = make_candles(50)
        result = IchimokuKijun().compute(candles, 26)
        assert result[0] == midpoint(candles, 0, 26)

    def test_too_few_candles_returns_empty(self):
        candles = make_candles(25)
        assert IchimokuKijun().compute(candles, 26) == []

    def test_plugin_attributes(self):
        assert IchimokuKijun.name == "ICHIMOKU_KIJUN"
        assert IchimokuKijun.default_period == 26


# ---------------------------------------------------------------------------
# IchimokuSpanA
# ---------------------------------------------------------------------------


class TestIchimokuSpanA:
    def test_output_length(self):
        # N candles, period=26 (displacement):
        # kijun produces N-25 values, displacement removes 26 -> N-51 values
        candles = make_candles(100)
        result = IchimokuSpanA().compute(candles, 26)
        assert len(result) == 100 - 51  # 49

    def test_too_few_candles_returns_empty(self):
        # Needs at least max(9,26) + 26 = 52 candles
        candles = make_candles(51)
        assert IchimokuSpanA().compute(candles, 26) == []

    def test_exactly_minimum_candles(self):
        candles = make_candles(52)
        result = IchimokuSpanA().compute(candles, 26)
        assert len(result) == 1

    def test_first_value_alignment(self):
        """
        span_a[0] maps to candles[N-len] in the registry.
        It should equal SpanA computed at T = (N-len) - 26.
        For N=100, len=49: maps to candles[51], computed at T=25.
        Tenkan at T=25 uses candles[17:26], Kijun at T=25 uses candles[0:26].
        """
        candles = make_candles(100)
        result = IchimokuSpanA().compute(candles, 26)

        t_at_25 = midpoint(candles, 17, 26)  # Tenkan window ending at idx 25
        k_at_25 = midpoint(candles, 0, 26)   # Kijun window ending at idx 25
        expected = (t_at_25 + k_at_25) / Decimal("2")

        assert result[0] == expected

    def test_plugin_attributes(self):
        assert IchimokuSpanA.name == "ICHIMOKU_SPAN_A"
        assert IchimokuSpanA.default_period == 26


# ---------------------------------------------------------------------------
# IchimokuSpanB
# ---------------------------------------------------------------------------


class TestIchimokuSpanB:
    def test_output_length(self):
        # N candles, period=52, displacement=26 -> (N-51) values
        candles = make_candles(100)
        result = IchimokuSpanB().compute(candles, 52)
        assert len(result) == 100 - 52 - 26 + 1  # 23

    def test_too_few_candles_returns_empty(self):
        # midpoint needs 52 candles -> 1 value; then displacement=26 means need >26
        candles = make_candles(77)  # 77-52+1=26 values, 26 <= 26 → empty
        assert IchimokuSpanB().compute(candles, 52) == []

    def test_exactly_minimum_candles(self):
        candles = make_candles(78)
        result = IchimokuSpanB().compute(candles, 52)
        assert len(result) == 1

    def test_first_value(self):
        """
        span_b[0] should be (highest high + lowest low) / 2 of candles[0:52].
        """
        candles = make_candles(100)
        result = IchimokuSpanB().compute(candles, 52)
        expected = midpoint(candles, 0, 52)
        assert result[0] == expected

    def test_displacement_hardcoded_26(self):
        """SpanB displacement is always 26 regardless of period."""
        candles = make_candles(100)
        result = IchimokuSpanB().compute(candles, 52)
        # midpoint series has 100-52+1=49 values; after [:-26] -> 23 values
        assert len(result) == 23

    def test_plugin_attributes(self):
        assert IchimokuSpanB.name == "ICHIMOKU_SPAN_B"
        assert IchimokuSpanB.default_period == 52


# ---------------------------------------------------------------------------
# IchimokuChikou
# ---------------------------------------------------------------------------


class TestIchimokuChikou:
    def test_output_length(self):
        candles = make_candles(100)
        result = IchimokuChikou().compute(candles, 26)
        assert len(result) == 100 - 26  # 74

    def test_too_few_candles_returns_empty(self):
        candles = make_candles(26)
        assert IchimokuChikou().compute(candles, 26) == []

    def test_exactly_minimum_candles(self):
        candles = make_candles(27)
        result = IchimokuChikou().compute(candles, 26)
        assert len(result) == 1

    def test_values_are_closes_shifted_back(self):
        """
        chikou[0] maps to candles[26] (registry offset=26).
        That value should be candles[0].close (26 periods back).
        """
        candles = make_candles(100)
        result = IchimokuChikou().compute(candles, 26)

        assert result[0] == candles[0].close
        assert result[1] == candles[1].close
        assert result[-1] == candles[73].close

    def test_plugin_attributes(self):
        assert IchimokuChikou.name == "ICHIMOKU_CHIKOU"
        assert IchimokuChikou.default_period == 26


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


class TestIchimokuRegistryIntegration:
    def test_all_ichimoku_plugins_discovered(self):
        registry = create_indicator_registry("plugins/indicators")
        for name in ("ICHIMOKU_TENKAN", "ICHIMOKU_KIJUN", "ICHIMOKU_SPAN_A",
                     "ICHIMOKU_SPAN_B", "ICHIMOKU_CHIKOU"):
            assert registry.is_registered(name), f"{name} not registered"

    def test_default_periods(self):
        registry = create_indicator_registry("plugins/indicators")
        assert registry.get_default_period("ICHIMOKU_TENKAN") == 9
        assert registry.get_default_period("ICHIMOKU_KIJUN") == 26
        assert registry.get_default_period("ICHIMOKU_SPAN_A") == 26
        assert registry.get_default_period("ICHIMOKU_SPAN_B") == 52
        assert registry.get_default_period("ICHIMOKU_CHIKOU") == 26

    def test_registry_returns_date_aligned_tuples(self):
        registry = create_indicator_registry("plugins/indicators")
        candles = make_candles(100)

        for name, period in [
            ("ICHIMOKU_TENKAN", 9),
            ("ICHIMOKU_KIJUN", 26),
            ("ICHIMOKU_SPAN_A", 26),
            ("ICHIMOKU_SPAN_B", 52),
            ("ICHIMOKU_CHIKOU", 26),
        ]:
            result = registry.compute(name, candles, period)
            assert len(result) > 0, f"{name} returned no values"
            for d, v in result:
                assert isinstance(d, date)
                assert isinstance(v, Decimal)

    def test_registry_dates_align_to_candles_end(self):
        """All components should end on the last candle's date."""
        registry = create_indicator_registry("plugins/indicators")
        candles = make_candles(100)
        last_date = candles[-1].date

        for name, period in [
            ("ICHIMOKU_TENKAN", 9),
            ("ICHIMOKU_KIJUN", 26),
            ("ICHIMOKU_CHIKOU", 26),
        ]:
            result = registry.compute(name, candles, period)
            assert result[-1][0] == last_date, (
                f"{name}: last date {result[-1][0]} != {last_date}"
            )

    def test_span_a_ends_on_last_candle(self):
        """
        SpanA and SpanB use displacement to shift which *computation* is shown
        at today's candle, but the registry date-aligns to the END of the candle
        list. So their last date is still the last candle's date.
        The VALUE at that date is the cloud computed 26 days earlier.
        """
        registry = create_indicator_registry("plugins/indicators")
        candles = make_candles(100)
        last_date = candles[-1].date

        for name, period in [("ICHIMOKU_SPAN_A", 26), ("ICHIMOKU_SPAN_B", 52)]:
            result = registry.compute(name, candles, period)
            assert result[-1][0] == last_date, (
                f"{name}: last date {result[-1][0]} != {last_date}"
            )
