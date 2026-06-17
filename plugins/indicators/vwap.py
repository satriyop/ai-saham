"""
Market VWAP Indicator Plugin.

Computes the volume-weighted average price across all market participants
over a rolling window of daily candles. Uses the standard Typical Price:
  TypicalPrice = (High + Low + Close) / 3

Interpretation:
  VWAP > current_price → price is below market average cost basis
    Constructive for accumulation — entering cheaper than average participant
  VWAP < current_price → price is above market average cost basis
    Chasing — paying more than the average participant over the window

This is distinct from FOREIGN_VWAP (foreigners' cost basis).
VWAP = all participants; FOREIGN_VWAP = foreign institutional buyers only.

Layer: Plugin / Infrastructure
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle


class VwapIndicator(IndicatorPlugin):
    """
    Market volume-weighted average price (rolling window).

    Formula: sum((H + L + C) / 3 * Volume, N days) / sum(Volume, N days)

    Returns a series aligned to candles. Values shorter than candles by
    (period - 1) due to warm-up.
    """

    name = "VWAP"
    default_period = 20

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        if not candles or period < 1:
            return []

        result: list[Decimal] = []
        for i in range(len(candles)):
            window = candles[max(0, i - period + 1) : i + 1]
            total_vol = sum(c.volume for c in window)
            if total_vol == 0:
                result.append(Decimal("0"))
                continue
            total_tpv = sum(
                (c.high + c.low + c.close) / Decimal("3") * c.volume
                for c in window
            )
            result.append((total_tpv / total_vol).quantize(Decimal("0.01")))

        return result
