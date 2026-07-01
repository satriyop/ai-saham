"""
Indicator registry for unified indicator computation.

Layer: Application (Service)
Purpose: Central registry that unifies built-in indicators, plugins, and formulas.

The registry stores callable compute functions. Built-in domain functions
are wrapped without modification. Plugin indicators are adapted to match
the same interface. Formula indicators are parsed and evaluated dynamically.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle
from src.domain.indicators import calculate_ema, calculate_rsi, calculate_sma

if TYPE_CHECKING:
    from src.application.formula.ast_nodes import ASTNode
    from src.domain.ports.broker_data_repository import BrokerDataRepository
    from src.domain.ports.market_data_repository import MarketDataRepository

# Type alias for indicator compute functions
# Takes candles and period, returns date-aligned values
IndicatorFn = Callable[[list[Candle], int], list[tuple[date, Decimal]]]

# Built-in indicator names (reserved, cannot be overridden)
BUILTIN_NAMES = frozenset({"SMA", "EMA", "RSI"})


class PluginRegistrationError(Exception):
    """Raised when plugin registration fails."""

    pass


class FormulaRegistrationError(Exception):
    """Raised when formula registration fails."""

    pass


class IndicatorRegistry:
    """
    Central registry for all indicator types.

    Provides a unified compute() interface for:
    - Built-in indicators (SMA, EMA, RSI)
    - Developer-provided plugins
    - Formula-based composite indicators

    Built-in indicators are handled directly by calling domain functions.
    Plugin indicators are wrapped to handle date alignment.
    Formula indicators are evaluated using the formula engine.
    """

    def __init__(
        self,
        broker_repository: "BrokerDataRepository | None" = None,
        market_repository: "MarketDataRepository | None" = None,
        index_ticker: str = "IHSG",
    ) -> None:
        """Initialize with empty plugin and formula registries."""
        self._plugins: dict[str, tuple[type[IndicatorPlugin], int]] = {}
        self._formulas: dict[str, "ASTNode"] = {}
        self._current_candles: list[Candle] | None = None
        self._broker_repository: "BrokerDataRepository | None" = broker_repository
        self._market_repository: "MarketDataRepository | None" = market_repository
        self._index_ticker: str = index_ticker

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

        if name in self._formulas:
            raise PluginRegistrationError(
                f"'{name}' conflicts with registered formula"
            )

        self._plugins[name] = (plugin_class, plugin_class.default_period)

    def register_formula(self, name: str, ast: "ASTNode") -> None:
        """
        Register a formula indicator with its parsed AST.

        The AST should be pre-validated using the formula validator
        to ensure all references exist and no cycles are present.

        Args:
            name: Formula indicator name
            ast: Parsed formula AST

        Raises:
            FormulaRegistrationError: If name conflicts or is invalid
        """
        name_upper = name.upper()

        if name_upper in BUILTIN_NAMES:
            raise FormulaRegistrationError(
                f"'{name}' conflicts with built-in indicator"
            )

        if name_upper in self._plugins:
            raise FormulaRegistrationError(
                f"'{name}' conflicts with registered plugin"
            )

        if name_upper in self._formulas:
            raise FormulaRegistrationError(f"'{name}' already registered")

        self._formulas[name_upper] = ast

    def get_series(self, name: str) -> list[Decimal]:
        """
        Get series by name (price field or indicator).

        This method is used by the FormulaEvaluator during formula computation.
        It requires _current_candles to be set via compute().

        Args:
            name: OPEN, HIGH, LOW, CLOSE, VOLUME, or indicator name

        Returns:
            Index-aligned list[Decimal] values

        Raises:
            RuntimeError: If called outside compute() context
            ValueError: If indicator name is unknown
        """
        if self._current_candles is None:
            raise RuntimeError(
                "get_series() must be called within compute() context"
            )

        candles = self._current_candles
        name_upper = name.upper()

        # Price series
        if name_upper == "OPEN":
            return [c.open for c in candles]
        if name_upper == "HIGH":
            return [c.high for c in candles]
        if name_upper == "LOW":
            return [c.low for c in candles]
        if name_upper == "CLOSE":
            return [c.close for c in candles]
        if name_upper == "VOLUME":
            return [Decimal(c.volume) for c in candles]

        # Indicator series - compute with default period
        period = self.get_default_period(name_upper)
        result = self.compute(name_upper, candles, period)
        return [v for _, v in result]  # Strip dates, keep values

    def compute(
        self,
        name: str,
        candles: list[Candle],
        period: int,
        price_field: str = "close",
    ) -> list[tuple[date, Decimal]]:
        """
        Compute indicator values.

        Dispatches to built-in domain functions, registered plugins,
        or formula evaluator based on indicator type.

        Args:
            name: Indicator name (e.g., "SMA", "RSI", "ATR", or formula name)
            candles: Historical price data, sorted by date ascending
            period: Calculation period (ignored for formulas)
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

        # Formula indicators
        if name_upper in self._formulas:
            return self._compute_formula(name_upper, candles)

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

        # Broker-aware plugins (FOREIGN_FLOW etc.) expose set_broker_data().
        if hasattr(plugin, "set_broker_data") and self._broker_repository and candles:
            ticker = candles[0].ticker
            summaries = self._broker_repository.get_broker_summaries(ticker)
            plugin.set_broker_data(summaries)

        # Index-aware plugins (RS_IHSG) expose set_index_candles().
        if hasattr(plugin, "set_index_candles") and self._market_repository:
            index_candles = self._market_repository.get_candles(self._index_ticker)
            plugin.set_index_candles(index_candles)

        values = plugin.compute(candles, period)

        if not values:
            return []

        # Values align to end of candles (after warm-up period)
        # Example: 100 candles, 86 values -> values[0] maps to candles[14]
        offset = len(candles) - len(values)

        return [
            (candles[offset + i].date, value) for i, value in enumerate(values)
        ]

    def _compute_formula(
        self,
        name: str,
        candles: list[Candle],
    ) -> list[tuple[date, Decimal]]:
        """
        Compute formula indicator values.

        Sets up candle context and uses the formula evaluator.

        Args:
            name: Formula name (uppercase)
            candles: Historical price data

        Returns:
            List of (date, value) tuples
        """
        # Import here to avoid circular dependency
        from src.application.formula.evaluator import (
            FormulaEvaluator,
            RegistrySeriesProvider,
        )

        if not candles:
            return []

        ast = self._formulas[name]

        # Set up candle context for get_series() calls
        self._current_candles = candles
        try:
            provider = RegistrySeriesProvider(self, candles)
            evaluator = FormulaEvaluator(provider)
            values = evaluator.compute(ast, len(candles))

            if not values:
                return []

            # Align values to dates (values align to end of candles)
            start_idx = len(candles) - len(values)
            return [
                (candles[start_idx + i].date, v)
                for i, v in enumerate(values)
            ]
        finally:
            self._current_candles = None

    def is_registered(self, name: str) -> bool:
        """
        Check if indicator name is available (built-in, plugin, or formula).

        Args:
            name: Indicator name to check

        Returns:
            True if indicator can be computed
        """
        name_upper = name.upper()
        return (
            name_upper in BUILTIN_NAMES
            or name_upper in self._plugins
            or name_upper in self._formulas
        )

    def get_default_period(self, name: str) -> int:
        """
        Get default period for an indicator.

        For formulas, returns 0 as period is embedded in the formula.

        Args:
            name: Indicator name

        Returns:
            Default period value (0 for formulas)

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

        # Formula indicators have no default period (embedded in formula)
        if name_upper in self._formulas:
            return 0

        raise ValueError(f"Unknown indicator: {name}")

    def list_indicators(self) -> list[str]:
        """
        List all available indicator names.

        Returns:
            Sorted list of indicator names (built-in + plugins + formulas)
        """
        all_names = (
            set(BUILTIN_NAMES)
            | set(self._plugins.keys())
            | set(self._formulas.keys())
        )
        return sorted(all_names)

    def list_formulas(self) -> list[str]:
        """
        List all registered formula indicator names.

        Returns:
            Sorted list of formula names
        """
        return sorted(self._formulas.keys())

    def get_available_indicators(self) -> set[str]:
        """
        Get set of all available indicator names.

        Useful for formula validation to check if references exist.

        Returns:
            Set of uppercase indicator names
        """
        return (
            set(BUILTIN_NAMES)
            | set(self._plugins.keys())
            | set(self._formulas.keys())
        )
