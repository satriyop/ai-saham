"""Registry adapter that wraps IndicatorRegistry as a SeriesProvider.

This module provides the concrete SeriesProvider implementation that
connects FormulaEvaluator to the IndicatorRegistry for price data and
indicator computation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.entities.candle import Candle


class RegistrySeriesProvider:
    """SeriesProvider implementation wrapping IndicatorRegistry.

    This adapter connects the FormulaEvaluator to the IndicatorRegistry,
    managing candle context and series extraction.

    Usage:
        provider = RegistrySeriesProvider(registry, candles)
        evaluator = FormulaEvaluator(provider)
        values = evaluator.compute(ast, len(candles))
    """

    def __init__(
        self,
        registry: "IndicatorRegistry",  # Forward reference
        candles: list["Candle"],
    ) -> None:
        """Initialize the provider.

        Args:
            registry: The indicator registry.
            candles: Candle data for computation.
        """
        self._registry = registry
        self._candles = candles

    def get_series(self, name: str) -> list[Decimal]:
        """Get a series by name.

        Args:
            name: OPEN, HIGH, LOW, CLOSE, VOLUME, or indicator name.

        Returns:
            List of Decimal values.
        """
        name_upper = name.upper()

        if name_upper == "OPEN":
            return [c.open for c in self._candles]
        elif name_upper == "HIGH":
            return [c.high for c in self._candles]
        elif name_upper == "LOW":
            return [c.low for c in self._candles]
        elif name_upper == "CLOSE":
            return [c.close for c in self._candles]
        elif name_upper == "VOLUME":
            return [Decimal(c.volume) for c in self._candles]

        period = self._registry.get_default_period(name_upper)
        result = self._registry.compute(name_upper, self._candles, period)
        return [v for _, v in result]

    def compute_indicator(self, name: str, period: int) -> list[Decimal]:
        """Compute an indicator with the given period.

        Args:
            name: Indicator name.
            period: Calculation period.

        Returns:
            List of Decimal values.
        """
        result = self._registry.compute(name, self._candles, period)
        return [v for _, v in result]

    def get_default_period(self, name: str) -> int:
        """Get the default period for an indicator.

        Args:
            name: Indicator name.

        Returns:
            Default period value.
        """
        return self._registry.get_default_period(name)


if TYPE_CHECKING:
    from src.application.services.indicator_registry import IndicatorRegistry
