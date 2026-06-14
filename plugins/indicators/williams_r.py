"""
Williams %R indicator plugin.

Momentum oscillator measuring close relative to the N-period high-low range.
Widely used by Indonesian retail and semi-professional traders on platforms
like Stockbit, RTI, and Ajaib. Inverse of Stochastic oscillator.

Formula:
  %R = (Highest High[N] - Close) / (Highest High[N] - Lowest Low[N]) × -100

Range: -100 to 0
  Above -20 : overbought (price near top of range)
  Below -80 : oversold  (price near bottom of range)

Usage in rules:
  left: { indicator: williams_r }
  operator: "<"
  right: { value: -80 }    # oversold entry
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

_MINUS_100 = Decimal("-100")
_MINUS_50 = Decimal("-50")


class WilliamsRIndicator(IndicatorPlugin):
    """Williams %R: momentum oscillator in range [-100, 0]."""

    name = "WILLIAMS_R"
    default_period = 14

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Compute Williams %R values.

        Args:
            candles: Price data sorted by date ascending
            period: Lookback window (typically 14)

        Returns:
            List of %R values in [-100, 0].
            Length = len(candles) - period + 1.
        """
        if len(candles) < period:
            return []

        result: list[Decimal] = []

        for i in range(period - 1, len(candles)):
            window = candles[i - period + 1:i + 1]
            highest = max(c.high for c in window)
            lowest = min(c.low for c in window)
            close = candles[i].close

            if highest == lowest:
                result.append(_MINUS_50)
            else:
                wr = (highest - close) / (highest - lowest) * _MINUS_100
                result.append(wr.quantize(Decimal("0.01")))

        return result
