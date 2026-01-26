"""
Indicator Plugin Template

Copy this file and rename it (remove the underscore prefix) to create a new
indicator plugin. Files starting with _ are not loaded by the plugin system.

See README.md in this directory for detailed documentation.
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle


class MyIndicator(IndicatorPlugin):
    """
    Replace with your indicator description.

    Explain what this indicator measures and when it's useful.
    """

    # REQUIRED: Unique uppercase identifier for this indicator
    # Must match pattern: ^[A-Z0-9_]+$
    # Examples: "SMA", "RSI", "BOLLINGER_BANDS", "EMA200"
    name = "MY_INDICATOR"

    # REQUIRED: Default period when none specified
    default_period = 14

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Compute indicator values for the given candle data.

        Args:
            candles: Price data sorted by date ASCENDING (oldest first).
                     Each candle has: date, open, high, low, close, volume
            period: Lookback period for calculation

        Returns:
            List of Decimal values. The length should typically be:
            len(candles) - period + 1 (for indicators like SMA)
            or len(candles) - period (for indicators requiring previous close like ATR)

            Values align to the END of the candle list:
            - result[0] corresponds to candles[period-1] (or similar)
            - result[-1] corresponds to candles[-1] (most recent)

        Raises:
            Return empty list [] if insufficient data, don't raise exceptions.
        """
        # Early return if not enough data
        if len(candles) < period:
            return []

        result: list[Decimal] = []

        # Example: Simple Moving Average implementation
        # for i in range(period - 1, len(candles)):
        #     window = candles[i - period + 1 : i + 1]
        #     avg = sum(c.close for c in window) / Decimal(period)
        #     result.append(avg)

        # TODO: Implement your indicator logic here

        return result
