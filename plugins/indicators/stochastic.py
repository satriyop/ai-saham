"""
Stochastic Oscillator (%K) indicator plugin.

%K = (close - lowest_low_N) / (highest_high_N - lowest_low_N) * 100

Range: 0-100. Oversold < 20, overbought > 80.
Warmup: N candles.
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

_HUNDRED = Decimal("100")


class StochasticIndicator(IndicatorPlugin):
    """Stochastic %K oscillator."""

    name = "STOCHASTIC"
    default_period = 14

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Args:
            candles: Price data sorted ascending
            period: Lookback period (typically 14)

        Returns:
            %K values (0-100); length = len(candles) - period + 1
        """
        if len(candles) < period:
            return []

        result = []
        for i in range(period - 1, len(candles)):
            window = candles[i - period + 1 : i + 1]
            highest = max(c.high for c in window)
            lowest = min(c.low for c in window)
            close = candles[i].close

            if highest == lowest:
                result.append(Decimal("50"))
            else:
                k = (close - lowest) / (highest - lowest) * _HUNDRED
                result.append(k)

        return result
