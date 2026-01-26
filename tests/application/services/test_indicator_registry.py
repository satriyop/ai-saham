"""
Tests for IndicatorRegistry.

Tests cover:
- Built-in indicator computation (SMA, EMA, RSI)
- Plugin registration and computation
- Error handling (conflicts, unknown indicators)
- Helper methods (is_registered, get_default_period, list_indicators)
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.application.services.indicator_registry import (
    BUILTIN_NAMES,
    IndicatorRegistry,
    PluginRegistrationError,
)
from src.domain.entities.candle import Candle


# ============================================================================
# Test Fixtures
# ============================================================================


def make_candle(days_ago: int, close: str = "1000.00") -> Candle:
    """Create a test candle."""
    price = Decimal(close)
    return Candle(
        ticker="TEST",
        date=date.today() - timedelta(days=days_ago),
        open=price,
        high=price + Decimal("10"),
        low=price - Decimal("10"),
        close=price,
        volume=100000,
    )


def make_trending_candles(count: int, start_price: float = 100.0) -> list[Candle]:
    """Create candles with upward trend for indicator testing."""
    candles = []
    for i in range(count - 1, -1, -1):
        price = Decimal(str(start_price + (count - 1 - i) * 5))
        candles.append(
            Candle(
                ticker="TEST",
                date=date.today() - timedelta(days=i),
                open=price,
                high=price + Decimal("10"),
                low=price - Decimal("5"),
                close=price,
                volume=100000,
            )
        )
    return candles


class MockPlugin(IndicatorPlugin):
    """Mock plugin for testing."""

    name = "MOCK"
    default_period = 10

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """Return constant values for testing."""
        if len(candles) < period:
            return []
        return [Decimal("42.00")] * (len(candles) - period + 1)


class AnotherMockPlugin(IndicatorPlugin):
    """Another mock plugin with different name."""

    name = "ANOTHER"
    default_period = 5

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        return [Decimal("99.00")] * (len(candles) - period + 1)


# ============================================================================
# Built-in Indicator Tests
# ============================================================================


class TestBuiltinIndicators:
    """Test that built-in indicators work through registry."""

    def test_compute_sma(self):
        """Should compute SMA correctly."""
        candles = make_trending_candles(30)
        registry = IndicatorRegistry()

        result = registry.compute("SMA", candles, period=10)

        assert len(result) > 0
        # All results should be (date, Decimal) tuples
        for d, value in result:
            assert isinstance(d, date)
            assert isinstance(value, Decimal)

    def test_compute_ema(self):
        """Should compute EMA correctly."""
        candles = make_trending_candles(30)
        registry = IndicatorRegistry()

        result = registry.compute("EMA", candles, period=10)

        assert len(result) > 0
        for d, value in result:
            assert isinstance(d, date)
            assert isinstance(value, Decimal)

    def test_compute_rsi(self):
        """Should compute RSI correctly."""
        candles = make_trending_candles(30)
        registry = IndicatorRegistry()

        result = registry.compute("RSI", candles, period=14)

        assert len(result) > 0
        for d, value in result:
            assert isinstance(d, date)
            assert isinstance(value, Decimal)
            # RSI should be between 0 and 100
            assert Decimal("0") <= value <= Decimal("100")

    def test_builtin_names_case_insensitive(self):
        """Should handle case-insensitive indicator names."""
        candles = make_trending_candles(30)
        registry = IndicatorRegistry()

        # All should work
        result_upper = registry.compute("SMA", candles, period=10)
        result_lower = registry.compute("sma", candles, period=10)
        result_mixed = registry.compute("Sma", candles, period=10)

        assert len(result_upper) == len(result_lower) == len(result_mixed)


# ============================================================================
# Plugin Registration Tests
# ============================================================================


class TestPluginRegistration:
    """Test plugin registration behavior."""

    def test_register_valid_plugin(self):
        """Should register a valid plugin."""
        registry = IndicatorRegistry()

        registry.register_plugin(MockPlugin)

        assert registry.is_registered("MOCK")

    def test_reject_builtin_name_conflict(self):
        """Should reject plugin that conflicts with built-in name."""

        class BadPlugin(IndicatorPlugin):
            name = "SMA"  # Conflicts!
            default_period = 10

            def compute(self, candles, period):
                return []

        registry = IndicatorRegistry()

        with pytest.raises(PluginRegistrationError, match="conflicts with built-in"):
            registry.register_plugin(BadPlugin)

    def test_reject_duplicate_registration(self):
        """Should reject duplicate plugin registration."""
        registry = IndicatorRegistry()
        registry.register_plugin(MockPlugin)

        with pytest.raises(PluginRegistrationError, match="already registered"):
            registry.register_plugin(MockPlugin)

    def test_reject_plugin_missing_name(self):
        """Should reject plugin without name attribute."""

        class NoNamePlugin(IndicatorPlugin):
            default_period = 10

            def compute(self, candles, period):
                return []

        # Remove name attribute if inherited
        if hasattr(NoNamePlugin, "name"):
            delattr(NoNamePlugin, "name")

        registry = IndicatorRegistry()

        with pytest.raises(PluginRegistrationError, match="missing"):
            registry.register_plugin(NoNamePlugin)

    def test_reject_plugin_missing_period(self):
        """Should reject plugin without default_period attribute."""

        class NoPeriodPlugin(IndicatorPlugin):
            name = "NOPERIOD"

            def compute(self, candles, period):
                return []

        # Remove default_period if inherited
        if hasattr(NoPeriodPlugin, "default_period"):
            delattr(NoPeriodPlugin, "default_period")

        registry = IndicatorRegistry()

        with pytest.raises(PluginRegistrationError, match="missing"):
            registry.register_plugin(NoPeriodPlugin)


# ============================================================================
# Plugin Computation Tests
# ============================================================================


class TestPluginComputation:
    """Test computing plugin indicators."""

    def test_compute_plugin_indicator(self):
        """Should compute plugin indicator values."""
        candles = make_trending_candles(30)
        registry = IndicatorRegistry()
        registry.register_plugin(MockPlugin)

        result = registry.compute("MOCK", candles, period=10)

        assert len(result) > 0
        # MockPlugin returns 42.00 for all values
        for d, value in result:
            assert isinstance(d, date)
            assert value == Decimal("42.00")

    def test_plugin_date_alignment(self):
        """Plugin results should align to correct dates."""
        candles = make_trending_candles(20)
        registry = IndicatorRegistry()
        registry.register_plugin(MockPlugin)

        result = registry.compute("MOCK", candles, period=10)

        # MockPlugin returns len(candles) - period + 1 values
        # For 20 candles, period 10: 20 - 10 + 1 = 11 values
        assert len(result) == 11

        # First result should align to candles[9] (after warm-up)
        # Last result should align to candles[19] (last candle)
        assert result[-1][0] == candles[-1].date

    def test_compute_unknown_indicator_raises(self):
        """Should raise ValueError for unknown indicator."""
        candles = make_trending_candles(30)
        registry = IndicatorRegistry()

        with pytest.raises(ValueError, match="Unknown indicator"):
            registry.compute("UNKNOWN", candles, period=10)


# ============================================================================
# Helper Method Tests
# ============================================================================


class TestHelperMethods:
    """Test registry helper methods."""

    def test_is_registered_builtins(self):
        """Built-in indicators should be registered."""
        registry = IndicatorRegistry()

        for name in BUILTIN_NAMES:
            assert registry.is_registered(name)
            assert registry.is_registered(name.lower())

    def test_is_registered_plugin(self):
        """Registered plugin should be found."""
        registry = IndicatorRegistry()
        registry.register_plugin(MockPlugin)

        assert registry.is_registered("MOCK")
        assert registry.is_registered("mock")
        assert not registry.is_registered("NOTREGISTERED")

    def test_get_default_period_builtins(self):
        """Should return correct default periods for built-ins."""
        registry = IndicatorRegistry()

        assert registry.get_default_period("RSI") == 14
        assert registry.get_default_period("SMA") == 20
        assert registry.get_default_period("EMA") == 20

    def test_get_default_period_plugin(self):
        """Should return plugin's default period."""
        registry = IndicatorRegistry()
        registry.register_plugin(MockPlugin)

        assert registry.get_default_period("MOCK") == 10

    def test_get_default_period_unknown_raises(self):
        """Should raise for unknown indicator."""
        registry = IndicatorRegistry()

        with pytest.raises(ValueError, match="Unknown indicator"):
            registry.get_default_period("UNKNOWN")

    def test_list_indicators_empty(self):
        """Should list only built-ins when no plugins."""
        registry = IndicatorRegistry()

        indicators = registry.list_indicators()

        assert set(indicators) == BUILTIN_NAMES

    def test_list_indicators_with_plugins(self):
        """Should list built-ins and plugins."""
        registry = IndicatorRegistry()
        registry.register_plugin(MockPlugin)
        registry.register_plugin(AnotherMockPlugin)

        indicators = registry.list_indicators()

        expected = BUILTIN_NAMES | {"MOCK", "ANOTHER"}
        assert set(indicators) == expected
        # Should be sorted
        assert indicators == sorted(indicators)
