"""
Relative Strength vs IHSG (RS_IHSG) indicator plugin.

Compares stock's N-day return to IHSG's N-day return over the same period.
Stocks with RS > 1 during market corrections are the first to bounce and
the strongest candidates for accumulation — a core IDX screening concept.

Formula:
  stock_return  = (Close[today] - Close[today-N]) / Close[today-N]
  ihsg_return   = (IHSG[today] - IHSG[today-N])  / IHSG[today-N]
  RS_IHSG       = stock_return / ihsg_return  (1.0 = matches IHSG)

Interpretation:
  RS > 1.0 : outperforming IHSG (relatively strong)
  RS < 1.0 : underperforming IHSG (relatively weak)
  RS = 1.0 : neutral / no index data available

Requires IHSG data in local DB:
  saham fetch ^JKSE --days 365

This is a broker-aware plugin — it requires index candles to be injected
via set_index_candles() before compute() is called. The registry handles
this automatically when a market_repository is configured.
"""

from datetime import date
from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.candle import Candle

_ONE = Decimal("1")
_ZERO = Decimal("0")


class RelativeStrengthIHSGIndicator(IndicatorPlugin):
    """
    Relative Strength vs IHSG index.

    RS > 1 = stock outperforming the market.
    RS < 1 = stock underperforming the market.
    """

    name = "RS_IHSG"
    default_period = 20

    def __init__(self) -> None:
        self._ihsg_by_date: dict[date, Decimal] = {}

    def set_index_candles(self, candles: list[Candle]) -> None:
        """
        Inject IHSG candles for RS computation.

        Called automatically by IndicatorRegistry when market_repository
        is configured. Must be called before compute().

        Args:
            candles: IHSG candles sorted by date ascending
        """
        self._ihsg_by_date = {c.date: c.close for c in candles}

    def compute(self, candles: list[Candle], period: int) -> list[Decimal]:
        """
        Compute RS vs IHSG for each candle.

        Args:
            candles: Stock price data sorted by date ascending
            period: Return lookback in trading days (default 20 ≈ 1 month)

        Returns:
            List of RS values. Length = len(candles) - period.
            Returns 1.0 for dates where IHSG data is missing.
        """
        if len(candles) <= period:
            return []

        result: list[Decimal] = []

        for i in range(period, len(candles)):
            stock_now = candles[i].close
            stock_prev = candles[i - period].close

            ihsg_now = self._ihsg_by_date.get(candles[i].date)
            ihsg_prev = self._ihsg_by_date.get(candles[i - period].date)

            if not ihsg_now or not ihsg_prev or stock_prev == _ZERO or ihsg_prev == _ZERO:
                result.append(_ONE)
                continue

            stock_return = (stock_now - stock_prev) / stock_prev
            ihsg_return = (ihsg_now - ihsg_prev) / ihsg_prev

            if ihsg_return == _ZERO:
                result.append(_ONE)
            else:
                rs = stock_return / ihsg_return
                result.append(rs.quantize(Decimal("0.0001")))

        return result
