"""
Ichimoku Kinko Hyo Indicator Plugin.

Provides the components of the Ichimoku system:
- Tenkan-sen (Conversion Line)
- Kijun-sen (Base Line)
- Senkou Span A (Leading Span A)
- Senkou Span B (Leading Span B)
- Chikou Span (Lagging Span)

This plugin allows users to fetch specific components by name.
Usage in rules/formulas:
  ICHIMOKU_TENKAN(9)
  ICHIMOKU_KIJUN(26)
  ICHIMOKU_SPAN_A(26) - Note: 26 is the displacement
  ICHIMOKU_SPAN_B(52)

Standard settings are 9, 26, 52.

Layer: Infrastructure (Plugin)
"""

from decimal import Decimal
from typing import List

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle


class IchimokuBase:
    """Base logic for Ichimoku components. 
    
    Not a subclass of IndicatorPlugin so the loader ignores it.
    """

    def _compute_midpoint(self, candles: List[Candle], period: int) -> List[Decimal]:
        """Compute (Highest High + Lowest Low) / 2 over period."""
        if len(candles) < period:
            return []

        results = []
        for i in range(period - 1, len(candles)):
            window = candles[i - period + 1 : i + 1]
            highest = max(c.high for c in window)
            lowest = min(c.low for c in window)
            midpoint = (highest + lowest) / Decimal("2")
            results.append(midpoint)
        
        return results


class IchimokuTenkan(IchimokuBase, IndicatorPlugin):
    """Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2."""
    name = "ICHIMOKU_TENKAN"
    default_period = 9

    def compute(self, candles: List[Candle], period: int) -> List[Decimal]:
        return self._compute_midpoint(candles, period)


class IchimokuKijun(IchimokuBase, IndicatorPlugin):
    """Kijun-sen (Base Line): (26-period high + 26-period low) / 2."""
    name = "ICHIMOKU_KIJUN"
    default_period = 26

    def compute(self, candles: List[Candle], period: int) -> List[Decimal]:
        return self._compute_midpoint(candles, period)


class IchimokuSpanA(IchimokuBase, IndicatorPlugin):
    """
    Senkou Span A (Leading Span A): (Tenkan + Kijun) / 2, plotted 26 periods ahead.
    
    Because the plugin system expects alignment with the current candle,
    this returns the Span A value for the CURRENT candle (which was computed 26 days ago).
    """
    name = "ICHIMOKU_SPAN_A"
    default_period = 26 # This is the displacement/kijun period

    def compute(self, candles: List[Candle], period: int) -> List[Decimal]:
        tenkan_period = 9
        kijun_period = 26
        displacement = period # Standard is 26

        if len(candles) < (max(tenkan_period, kijun_period) + displacement):
            return []

        # 1. Compute Tenkan and Kijun
        tenkan = IchimokuTenkan().compute(candles, tenkan_period)
        kijun = IchimokuKijun().compute(candles, kijun_period)

        # 2. Align them (Tenkan starts earlier than Kijun usually)
        # We need them to be the same length aligned to the end
        min_len = min(len(tenkan), len(kijun))
        t_aligned = tenkan[-min_len:]
        k_aligned = kijun[-min_len:]

        # 3. Compute (Tenkan + Kijun) / 2
        leading_span_a = [(t + k) / Decimal("2") for t, k in zip(t_aligned, k_aligned)]

        # 4. Displace: The value for 'today' is the one calculated 'displacement' days ago
        # To align with current candles, we return the series shifted
        if len(leading_span_a) <= displacement:
            return []
            
        return leading_span_a[:-displacement]


class IchimokuSpanB(IchimokuBase, IndicatorPlugin):
    """
    Senkou Span B (Leading Span B): (52-period high + 52-period low) / 2, plotted 26 periods ahead.
    """
    name = "ICHIMOKU_SPAN_B"
    default_period = 52 # Lookback period

    def compute(self, candles: List[Candle], period: int) -> List[Decimal]:
        displacement = 26
        
        # 1. Compute midpoint of lookback (default 52)
        midpoint = self._compute_midpoint(candles, period)
        
        # 2. Displace
        if len(midpoint) <= displacement:
            return []
            
        return midpoint[:-displacement]


class IchimokuChikou(IndicatorPlugin):
    """
    Chikou Span (Lagging Span): Current close plotted 26 periods back.
    For rule engine purposes, this returns the Close of 26 days ago.
    """
    name = "ICHIMOKU_CHIKOU"
    default_period = 26

    def compute(self, candles: List[Candle], period: int) -> List[Decimal]:
        displacement = period
        if len(candles) <= displacement:
            return []
        
        # The Chikou Span value for 'today' is actually the close from 'displacement' days ago
        # (Since today's close is plotted 26 days back, 26 days ago's close is what sits on today's candle)
        closes = [c.close for c in candles]
        return closes[:-displacement]
