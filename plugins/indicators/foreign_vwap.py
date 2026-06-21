"""
Foreign VWAP Indicator Plugin.

Computes the volume-weighted average price of foreign buy transactions
over a rolling window. This answers: "At what average price have
foreigners been buying over the last N days?"

Interpretation:
  FOREIGN_VWAP > current_price → foreigners are "underwater" (bought higher)
    They tend to defend the position by buying more on weakness → price floor
  FOREIGN_VWAP < current_price → foreigners are in profit (bought cheaper)
    Classic smart money accumulation pattern

Requires broker summary data via set_broker_data() before compute().
Works with both IDX (aggregate) and Stockbit (per-broker) data sources.

Layer: Plugin / Infrastructure
"""

from datetime import date
from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.value_objects.idx_market import SHARES_PER_LOT


class ForeignVWAPIndicator(IndicatorPlugin):
    """
    Foreign volume-weighted average buy price.

    Computes: sum(foreign_buy_value) / (sum(foreign_buy_lot) * 100)
    over the rolling N-day window ending at each candle.

    Returns empty list when there are no buy lots in the window
    (prevents division by zero and avoids misleading zero values).
    """

    name = "FOREIGN_VWAP"
    default_period = 20

    def __init__(self) -> None:
        self._broker_summaries: dict[date, BrokerSummary] = {}

    def set_broker_data(self, summaries: list[BrokerSummary]) -> None:
        """Pre-load broker summaries before calling compute().

        Args:
            summaries: List of BrokerSummary entities for the ticker
        """
        self._broker_summaries = {s.date: s for s in summaries}

    def compute(
        self,
        candles: list[Candle],
        period: int,
    ) -> list[Decimal]:
        """Compute rolling foreign VWAP aligned to candle dates.

        Args:
            candles: List of candles (used for date alignment only)
            period: Rolling window size in days

        Returns:
            List of VWAP values per candle date.
            Returns Decimal("0") for dates with no foreign buy activity.
        """
        if not candles or period < 1:
            return []

        result: list[Decimal] = []

        for i, _candle in enumerate(candles):
            total_buy_value = Decimal("0")
            total_buy_lots = 0

            for j in range(max(0, i - period + 1), i + 1):
                candle_date = candles[j].date
                if candle_date in self._broker_summaries:
                    summary = self._broker_summaries[candle_date]
                    total_buy_value += summary.foreign_buy_value
                    total_buy_lots += summary.foreign_buy_lot

            if total_buy_lots > 0:
                vwap = total_buy_value / (total_buy_lots * SHARES_PER_LOT)
                result.append(vwap.quantize(Decimal("0.01")))
            else:
                result.append(Decimal("0"))

        return result
