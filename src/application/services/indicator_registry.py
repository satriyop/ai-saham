"""
Indicator registry for unified indicator computation.

Layer: Application (Service)
Purpose: Central registry that unifies built-in indicators and plugins.

The registry stores callable compute functions. Built-in domain functions
are wrapped without modification. Plugin indicators are adapted to match
the same interface.
"""

from datetime import date
from decimal import Decimal
from typing import Callable

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle
from src.domain.indicators import calculate_ema, calculate_rsi, calculate_sma

# Type alias for indicator compute functions
# Takes candles and period, returns date-aligned values
IndicatorFn = Callable[[list[Candle], int], list[tuple[date, Decimal]]]

# Built-in indicator names (reserved, cannot be overridden)
BUILTIN_NAMES = frozenset({"SMA", "EMA", "RSI"})


class PluginRegistrationError(Exception):
    """Raised when plugin registration fails."""

    pass


class IndicatorRegistry:
    """
    Central registry for all indicator types.

    Provides a unified compute() interface for both built-in indicators
    (SMA, EMA, RSI) and developer-provided plugins.

    Built-in indicators are handled directly by calling domain functions.
    Plugin indicators are wrapped to handle date alignment.
    """

    def __init__(self) -> None:
        """Initialize with empty plugin registry."""
        self._plugins: dict[str, tuple[type[IndicatorPlugin], int]] = {}
        # Maps name -> (plugin_class, default_period)

    def register_plugin(self, plugin_class: type[IndicatorPlugin]) -> None:
        """
        Register a plugin indicator.

        Args:
            plugin_class: IndicatorPlugin subclass with name and default_period

        Raises:
            PluginRegistrationError: If name conflicts with built-in or duplicate
        """
        if not hasattr(plugin_class, "name") or not hasattr(
            plugin_class, "default_period"
        ):
            raise PluginRegistrationError(
                f"Plugin {plugin_class.__name__} missing 'name' or 'default_period'"
            )

        name = plugin_class.name.upper()

        if name in BUILTIN_NAMES:
            raise PluginRegistrationError(
                f"'{name}' conflicts with built-in indicator"
            )

        if name in self._plugins:
            raise PluginRegistrationError(f"'{name}' already registered")

        self._plugins[name] = (plugin_class, plugin_class.default_period)

    def compute(
        self,
        name: str,
        candles: list[Candle],
        period: int,
        price_field: str = "close",
    ) -> list[tuple[date, Decimal]]:
        """
        Compute indicator values.

        Dispatches to built-in domain functions or registered plugins.

        Args:
            name: Indicator name (e.g., "SMA", "RSI", "ATR")
            candles: Historical price data, sorted by date ascending
            period: Calculation period
            price_field: Price field for moving averages (default: "close")

        Returns:
            List of (date, value) tuples, sorted by date ascending

        Raises:
            ValueError: If indicator name is unknown
        """
        name_upper = name.upper()

        # Built-in indicators - call domain functions directly
        if name_upper == "SMA":
            return calculate_sma(candles, period=period, price_field=price_field)
        elif name_upper == "EMA":
            return calculate_ema(candles, period=period, price_field=price_field)
        elif name_upper == "RSI":
            return calculate_rsi(candles, period=period)

        # Plugin indicators
        if name_upper in self._plugins:
            plugin_class, _ = self._plugins[name_upper]
            return self._compute_plugin(plugin_class, candles, period)

        raise ValueError(f"Unknown indicator: {name}")

    def _compute_plugin(
        self,
        plugin_class: type[IndicatorPlugin],
        candles: list[Candle],
        period: int,
    ) -> list[tuple[date, Decimal]]:
        """
        Compute plugin indicator and align with dates.

        Plugin returns list[Decimal], we align dates from candles.

        Args:
            plugin_class: The plugin class to instantiate
            candles: Historical price data
            period: Calculation period

        Returns:
            List of (date, value) tuples
        """
        plugin = plugin_class()
        values = plugin.compute(candles, period)

        if not values:
            return []

        # Values align to end of candles (after warm-up period)
        # Example: 100 candles, 86 values -> values[0] maps to candles[14]
        offset = len(candles) - len(values)

        return [
            (candles[offset + i].date, value) for i, value in enumerate(values)
        ]

    def is_registered(self, name: str) -> bool:
        """
        Check if indicator name is available (built-in or plugin).

        Args:
            name: Indicator name to check

        Returns:
            True if indicator can be computed
        """
        name_upper = name.upper()
        return name_upper in BUILTIN_NAMES or name_upper in self._plugins

    def get_default_period(self, name: str) -> int:
        """
        Get default period for an indicator.

        Args:
            name: Indicator name

        Returns:
            Default period value

        Raises:
            ValueError: If indicator unknown
        """
        name_upper = name.upper()

        # Built-in defaults
        if name_upper == "RSI":
            return 14
        if name_upper in ("SMA", "EMA"):
            return 20

        # Plugin defaults
        if name_upper in self._plugins:
            _, default_period = self._plugins[name_upper]
            return default_period

        raise ValueError(f"Unknown indicator: {name}")

    def list_indicators(self) -> list[str]:
        """
        List all available indicator names.

        Returns:
            Sorted list of indicator names (built-in + plugins)
        """
        all_names = set(BUILTIN_NAMES) | set(self._plugins.keys())
        return sorted(all_names)
