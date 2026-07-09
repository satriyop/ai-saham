"""
Donchian Channel indicator plugins.

Three plugins, one file:
  DonchianUpperIndicator — Upper band: Highest High of the previous N periods.
  DonchianLowerIndicator — Lower band: Lowest Low of the previous N periods.
  DonchianMiddleIndicator — Middle band: (Upper + Lower) / 2.

To allow breakout detection (e.g. CLOSE > DONCHIAN_UPPER), the window
excludes the current candle and looks back at the previous N candles.
Warmup: N + 1 candles.
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle


def _donchian_core(
    candles: list[Candle], period: int
) -> list[tuple[Decimal, Decimal, Decimal]]:
    """Return list of (mid, upper, lower) tuples, length = len(candles) - period."""
    if len(candles) <= period:
        return []

    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    result = []
    
    # At index i, we look back from i - period to i - 1 (excluding index i)
    for i in range(period, len(candles)):
        window_highs = highs[i - period : i]
        window_lows = lows[i - period : i]
        upper = max(window_highs)
        lower = min(window_lows)
        mid = (upper + lower) / Decimal("2")
        result.append((mid, upper, lower))
        
    return result


class DonchianUpperIndicator(IndicatorPlugin):
    """Upper Donchian Channel: Highest High of the previous N periods."""

    name = "DONCHIAN_UPPER"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        results = _donchian_core(candles, period)
        return [upper for _, upper, _ in results]


class DonchianLowerIndicator(IndicatorPlugin):
    """Lower Donchian Channel: Lowest Low of the previous N periods."""

    name = "DONCHIAN_LOWER"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        results = _donchian_core(candles, period)
        return [lower for _, _, lower in results]


class DonchianMiddleIndicator(IndicatorPlugin):
    """Middle Donchian Channel: (Upper + Lower) / 2."""

    name = "DONCHIAN_MIDDLE"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        results = _donchian_core(candles, period)
        return [mid for mid, _, _ in results]
