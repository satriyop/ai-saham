"""
Average True Range (ATR) indicator plugin.

ATR measures market volatility by calculating the average of true ranges
over a specified period. Useful for:
- Position sizing
- Setting stop-loss levels
- Identifying volatility breakouts

Formula:
    True Range = max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close)
    )
    ATR = Wilder's smoothed average of True Range
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle


class ATRIndicator(IndicatorPlugin):
    """
    Average True Range (ATR) indicator.

    Measures market volatility using Wilder's smoothing method.
    """

    name = "ATR"
    default_period = 14

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Compute ATR values.

        Args:
            candles: Price data sorted by date ascending
            period: ATR period (typically 14)

        Returns:
            List of ATR values. Length = len(candles) - period
        """
        if len(candles) < period + 1:
            return []

        # Step 1: Calculate True Range for each candle (starting from index 1)
        true_ranges: list[Decimal] = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i - 1].close

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
            true_ranges.append(tr)

        # Step 2: First ATR is simple average of first `period` true ranges
        first_atr = sum(true_ranges[:period], Decimal("0")) / Decimal(period)
        result: list[Decimal] = [first_atr]

        # Step 3: Wilder's smoothing for subsequent values
        # ATR = ((prior ATR × (period - 1)) + current TR) / period
        multiplier = Decimal(period - 1)
        divisor = Decimal(period)

        atr = first_atr
        for i in range(period, len(true_ranges)):
            atr = (atr * multiplier + true_ranges[i]) / divisor
            result.append(atr)

        return result
