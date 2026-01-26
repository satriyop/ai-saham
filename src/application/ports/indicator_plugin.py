"""
Indicator plugin interface for custom indicators.

Layer: Application (Port)
Purpose: Define contract for developer-created indicator plugins.

Plugins implement this interface and are discovered at startup.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import ClassVar

from src.domain.entities.candle import Candle


class IndicatorPlugin(ABC):
    """
    Abstract base class for indicator plugins.

    Developers create plugins by:
    1. Subclassing IndicatorPlugin
    2. Setting `name` and `default_period` class attributes
    3. Implementing `compute()` method

    Example:
        class ATRIndicator(IndicatorPlugin):
            name = "ATR"
            default_period = 14

            def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
                # Return values aligned to candles (shorter due to warm-up)
                ...
    """

    name: ClassVar[str]  # e.g., "ATR", "VWAP"
    default_period: ClassVar[int]  # e.g., 14

    @abstractmethod
    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Compute indicator values.

        Args:
            candles: List of Candle entities, sorted by date ascending
            period: Calculation period (e.g., 14 for ATR-14)

        Returns:
            List of Decimal values. Length may be shorter than candles
            due to warm-up period. Values align to END of candles list.

            Example: 100 candles, period 14 -> returns 86 values
                     (values[0] corresponds to candles[14])
        """
        ...
