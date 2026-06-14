"""
Money Flow Index (MFI) indicator plugin.

Volume-weighted RSI. Measures buying and selling pressure by combining
price momentum with volume conviction. More reliable than pure RSI on IDX
because volume is dominated by institutional flows that carry real signal.

Formula:
  Typical Price (TP) = (High + Low + Close) / 3
  Raw Money Flow  = TP × Volume
  Positive MF     = sum of RMF where TP > prev_TP (over N periods)
  Negative MF     = sum of RMF where TP ≤ prev_TP (over N periods)
  MFI             = 100 - 100 / (1 + Positive MF / Negative MF)

Interpretation:
  MFI > 80 : overbought
  MFI < 20 : oversold
  MFI < 30 : moderately oversold (softer entry filter)
"""

from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle


class MoneyFlowIndexIndicator(IndicatorPlugin):
    """Money Flow Index: volume-weighted momentum oscillator (0–100)."""

    name = "MFI"
    default_period = 14

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Compute MFI values.

        Args:
            candles: Price data sorted by date ascending
            period: MFI lookback period (typically 14)

        Returns:
            List of MFI values (0–100). Length = len(candles) - period.
        """
        if len(candles) < period + 1:
            return []

        two = Decimal("2")
        three = Decimal("3")

        typical_prices = [
            (c.high + c.low + c.close) / three for c in candles
        ]
        raw_money_flows = [
            typical_prices[i] * Decimal(str(candles[i].volume))
            for i in range(len(candles))
        ]

        result: list[Decimal] = []

        for i in range(period, len(candles)):
            pos_flow = Decimal("0")
            neg_flow = Decimal("0")

            for j in range(i - period + 1, i + 1):
                if typical_prices[j] > typical_prices[j - 1]:
                    pos_flow += raw_money_flows[j]
                else:
                    neg_flow += raw_money_flows[j]

            if neg_flow == Decimal("0"):
                mfi = Decimal("100")
            else:
                money_ratio = pos_flow / neg_flow
                mfi = Decimal("100") - Decimal("100") / (Decimal("1") + money_ratio)

            result.append(mfi.quantize(Decimal("0.01")))

        return result
