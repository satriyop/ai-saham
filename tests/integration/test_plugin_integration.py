"""
Integration tests for the plugin system.

Tests the full flow: plugin discovery -> registration -> computation -> use in rules.
"""

import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.services.bootstrap import create_indicator_registry
from src.application.services.indicator_registry import IndicatorRegistry
from src.domain.entities.candle import Candle
from src.infrastructure.plugins.indicator_loader import IndicatorPluginLoader


# ============================================================================
# Test Fixtures
# ============================================================================


def make_volatile_candles(count: int) -> list[Candle]:
    """Create candles with high/low spread for ATR testing."""
    candles = []
    base_price = 1000.0
    for i in range(count - 1, -1, -1):
        # Create volatility by varying high/low spread
        price = Decimal(str(base_price + (count - 1 - i) * 10))
        spread = Decimal("50") + Decimal(str((i % 5) * 10))  # Varying spread

        candles.append(
            Candle(
                ticker="TEST",
                date=date.today() - timedelta(days=i),
                open=price,
                high=price + spread,
                low=price - spread / 2,
                close=price + Decimal("5"),
                volume=100000,
            )
        )
    return candles


# ============================================================================
# ATR Plugin Integration Tests
# ============================================================================


class TestATRPluginIntegration:
    """Test ATR plugin works end-to-end."""

    def test_atr_plugin_discovered_from_project_plugins(self):
        """Should discover ATR plugin from plugins/indicators/."""
        loader = IndicatorPluginLoader(Path("plugins/indicators"))
        plugins = loader.discover()

        names = {p.name for p in plugins}
        assert "ATR" in names

    def test_atr_plugin_registered_in_registry(self):
        """Should register ATR plugin via bootstrap."""
        registry = create_indicator_registry("plugins/indicators")

        assert registry.is_registered("ATR")
        assert registry.get_default_period("ATR") == 14

    def test_atr_plugin_computes_values(self):
        """Should compute ATR values correctly."""
        registry = create_indicator_registry("plugins/indicators")
        candles = make_volatile_candles(30)

        result = registry.compute("ATR", candles, period=14)

        # Should have values (30 candles - 14 period - 1 for TR = 15 values)
        assert len(result) > 0

        # All values should be positive (ATR measures volatility magnitude)
        for d, value in result:
            assert isinstance(d, date)
            assert isinstance(value, Decimal)
            assert value > Decimal("0")

    def test_atr_plugin_in_full_registry(self):
        """ATR should appear in list of all indicators."""
        registry = create_indicator_registry("plugins/indicators")

        all_indicators = registry.list_indicators()

        assert "ATR" in all_indicators
        assert "SMA" in all_indicators
        assert "EMA" in all_indicators
        assert "RSI" in all_indicators


# ============================================================================
# Custom Plugin Tests
# ============================================================================


class TestCustomPluginIntegration:
    """Test creating and loading custom plugins."""

    def test_custom_plugin_full_flow(self):
        """Test creating, loading, and using a custom plugin."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a custom plugin
            plugin_code = '''
from decimal import Decimal
from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

class VolumeMAIndicator(IndicatorPlugin):
    """Simple volume moving average indicator."""

    name = "VOLUME_MA"
    default_period = 10

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        if len(candles) < period:
            return []

        result = []
        for i in range(period - 1, len(candles)):
            window = candles[i - period + 1 : i + 1]
            avg_volume = sum(c.volume for c in window) / period
            result.append(Decimal(str(avg_volume)))

        return result
'''
            plugin_path = Path(tmpdir) / "volume_ma.py"
            plugin_path.write_text(plugin_code)

            # Load via bootstrap
            registry = create_indicator_registry(tmpdir)

            # Verify registration
            assert registry.is_registered("VOLUME_MA")
            assert registry.get_default_period("VOLUME_MA") == 10

            # Compute values
            candles = make_volatile_candles(20)
            result = registry.compute("VOLUME_MA", candles, period=10)

            assert len(result) == 11  # 20 - 10 + 1 = 11 values

            # All values should be positive (volume average)
            for d, value in result:
                assert value > Decimal("0")


# ============================================================================
# Graceful Degradation Tests
# ============================================================================


class TestGracefulDegradation:
    """Test system works without plugins."""

    def test_registry_works_without_plugins(self):
        """Registry should work with only built-in indicators."""
        # Use non-existent plugin directory and disable formula loading
        # to test pure plugin graceful degradation
        registry = create_indicator_registry(
            plugin_dir="/nonexistent/plugins",
            load_formulas=False,
        )

        # Built-ins should work
        assert registry.is_registered("SMA")
        assert registry.is_registered("EMA")
        assert registry.is_registered("RSI")

        # List should contain only built-ins
        indicators = registry.list_indicators()
        assert set(indicators) == {"SMA", "EMA", "RSI"}

    def test_computation_works_without_plugins(self):
        """Should compute built-in indicators without plugins."""
        registry = create_indicator_registry("/nonexistent/plugins")
        candles = make_volatile_candles(30)

        # All built-ins should compute
        sma = registry.compute("SMA", candles, period=10)
        ema = registry.compute("EMA", candles, period=10)
        rsi = registry.compute("RSI", candles, period=14)

        assert len(sma) > 0
        assert len(ema) > 0
        assert len(rsi) > 0
