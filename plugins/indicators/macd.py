"""
MACD (Moving Average Convergence/Divergence) indicator plugins.

Two plugins in this file:
  MACDIndicator      — MACD line (fast EMA - slow EMA)
  MACDSignalIndicator — Signal line (EMA of MACD)

Warmup: slow_period (26) candles consumed before first value.
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

_TWO = Decimal("2")


def _ema_of_series(values: list[Decimal], period: int) -> list[Decimal]:
    """Compute EMA over a list of Decimal values (SMA-seeded)."""
    if len(values) < period:
        return []
    k = _TWO / (Decimal(period) + 1)
    one_minus_k = 1 - k
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    result = [seed]
    for v in values[period:]:
        result.append(v * k + result[-1] * one_minus_k)
    return result


class MACDIndicator(IndicatorPlugin):
    """MACD line = EMA(fast) - EMA(slow). Default: fast=12, slow=26."""

    name = "MACD"
    default_period = 12  # fast EMA period; slow is hardcoded at 26

    SLOW_PERIOD = 26

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Args:
            candles: Price data sorted ascending
            period: Fast EMA period (typically 12)

        Returns:
            MACD line values; length = len(candles) - SLOW_PERIOD
        """
        fast = period
        slow = self.SLOW_PERIOD
        if len(candles) < slow:
            return []

        closes = [c.close for c in candles]
        fast_ema = _ema_of_series(closes, fast)
        slow_ema = _ema_of_series(closes, slow)

        # Align: slow_ema has len = len(candles) - slow + 1
        # fast_ema has len = len(candles) - fast + 1
        # slow_ema is shorter; align by taking last len(slow_ema) values
        offset = len(fast_ema) - len(slow_ema)
        return [f - s for f, s in zip(fast_ema[offset:], slow_ema)]


class MACDSignalIndicator(IndicatorPlugin):
    """MACD Signal line = EMA(9) of the MACD line."""

    name = "MACD_SIGNAL"
    default_period = 9  # signal EMA period

    SLOW_PERIOD = 26
    FAST_PERIOD = 12

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Args:
            candles: Price data sorted ascending
            period: Signal EMA period (typically 9)

        Returns:
            Signal line values; length = len(candles) - SLOW_PERIOD - period + 1
        """
        fast = self.FAST_PERIOD
        slow = self.SLOW_PERIOD
        signal = period

        if len(candles) < slow + signal:
            return []

        closes = [c.close for c in candles]
        fast_ema = _ema_of_series(closes, fast)
        slow_ema = _ema_of_series(closes, slow)

        offset = len(fast_ema) - len(slow_ema)
        macd_line = [f - s for f, s in zip(fast_ema[offset:], slow_ema)]

        return _ema_of_series(macd_line, signal)
