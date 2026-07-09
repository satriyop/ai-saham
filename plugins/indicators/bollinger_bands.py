"""
Bollinger Bands indicator plugins.

Three plugins, one file:
  BollingerUpperIndicator — Upper band: SMA(N) + 2 * stddev(N)
  BollingerLowerIndicator — Lower band: SMA(N) - 2 * stddev(N)
  BollingerWidthIndicator — Width: (upper - lower) / SMA(N) * 100

Warmup: N candles.
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

_TWO = Decimal("2")


def _bollinger_core(
    candles: list[Candle], period: int
) -> list[tuple[Decimal, Decimal, Decimal]]:
    """Return list of (mid, upper, lower) tuples, length = len(candles) - period + 1."""
    closes = [c.close for c in candles]
    result = []
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        mid = sum(window, Decimal("0")) / Decimal(period)
        variance = sum((x - mid) ** 2 for x in window) / Decimal(period)
        std = variance.sqrt()
        upper = mid + _TWO * std
        lower = mid - _TWO * std
        result.append((mid, upper, lower))
    return result


class BollingerUpperIndicator(IndicatorPlugin):
    """Upper Bollinger Band: SMA(N) + 2 * stddev(N)."""

    name = "BB_UPPER"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        if len(candles) < period:
            return []
        return [upper for _, upper, _ in _bollinger_core(candles, period)]


class BollingerLowerIndicator(IndicatorPlugin):
    """Lower Bollinger Band: SMA(N) - 2 * stddev(N)."""

    name = "BB_LOWER"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        if len(candles) < period:
            return []
        return [lower for _, _, lower in _bollinger_core(candles, period)]


class BollingerWidthIndicator(IndicatorPlugin):
    """Bollinger Band Width: (upper - lower) / mid * 100. Squeeze detector."""

    name = "BB_WIDTH"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        if len(candles) < period:
            return []
        result = []
        for mid, upper, lower in _bollinger_core(candles, period):
            if mid == 0:
                result.append(Decimal("0"))
            else:
                result.append((upper - lower) / mid * 100)
        return result


class BollingerWidthT1Indicator(IndicatorPlugin):
    """Previous day's Bollinger Band Width (T-1). Squeeze detector helper."""

    name = "BB_WIDTH_T1"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        if len(candles) < period + 1:
            return []
        width_indicator = BollingerWidthIndicator()
        widths = width_indicator.compute(candles, period)
        return widths[:-1]

