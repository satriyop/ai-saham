"""
On-Balance Volume (OBV) indicator plugin.

Cumulative volume indicator that adds volume on up-days and subtracts on
down-days. Detects institutional accumulation/distribution where price
stays flat but OBV trends — the classic bandarmologi detection pattern
for IDX markets.

Formula:
  OBV[0] = Volume[0]
  OBV[i] = OBV[i-1] + Volume[i]  if Close[i] > Close[i-1]
  OBV[i] = OBV[i-1] - Volume[i]  if Close[i] < Close[i-1]
  OBV[i] = OBV[i-1]              if Close[i] = Close[i-1]

Usage: OBV values are absolute and stock-specific. Use in combination
with SMA(OBV) via a formula to detect OBV trend direction, or compare
OBV divergence vs price direction in rules.

Note: `period` parameter is not used in the standard OBV formula.
      It is accepted for interface compliance but ignored.
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle


class OnBalanceVolumeIndicator(IndicatorPlugin):
    """On-Balance Volume: cumulative volume flow direction indicator."""

    name = "OBV"
    default_period = 1  # OBV is cumulative; period unused

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Compute OBV for all candles.

        Args:
            candles: Price data sorted by date ascending
            period: Not used (OBV is cumulative from first candle)

        Returns:
            List of OBV values. Length = len(candles). No warmup period.
        """
        if not candles:
            return []

        obv = Decimal(str(candles[0].volume))
        result: list[Decimal] = [obv]

        for i in range(1, len(candles)):
            vol = Decimal(str(candles[i].volume))
            if candles[i].close > candles[i - 1].close:
                obv += vol
            elif candles[i].close < candles[i - 1].close:
                obv -= vol
            result.append(obv)

        return result
