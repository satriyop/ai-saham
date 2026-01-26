"""
Foreign Flow Indicator Plugin.

Computes foreign net buy/sell flow over a rolling period.
Uses broker summary data instead of price candles.

This is a special indicator that requires BrokerSummary data
rather than standard Candle data.

Usage in strategy YAML:
    indicators:
      foreign_flow_3d:
        type: FOREIGN_FLOW
        period: 3  # 3-day rolling sum

    rules:
      - name: foreign_accumulation
        when:
          left:
            indicator: foreign_flow_3d
          operator: ">"
          right:
            value: 50_000_000_000  # 50B IDR
        outcome: LOW_RISK
"""

from datetime import date
from decimal import Decimal

from src.application.ports.indicator_plugin import IndicatorPlugin
from src.domain.entities.broker_flow import BrokerSummary
from src.domain.entities.candle import Candle


class ForeignFlowIndicator(IndicatorPlugin):
    """
    Foreign net flow indicator.

    Computes rolling sum of foreign net buy/sell value.

    Positive values = foreign accumulation (net buying)
    Negative values = foreign distribution (net selling)

    Note: This indicator uses a separate data source (broker summaries).
    The compute() method expects candles but the actual values come from
    broker data that must be pre-loaded and aligned.
    """

    name = "FOREIGN_FLOW"
    default_period = 1  # Single day by default

    def __init__(self) -> None:
        """Initialize indicator."""
        self._broker_summaries: dict[date, BrokerSummary] = {}

    def set_broker_data(self, summaries: list[BrokerSummary]) -> None:
        """
        Set broker summary data for indicator computation.

        Must be called before compute() to provide broker data.

        Args:
            summaries: List of BrokerSummary entities
        """
        self._broker_summaries = {s.date: s for s in summaries}

    def compute(
        self,
        candles: list[Candle],
        period: int,
    ) -> list[Decimal]:
        """
        Compute rolling foreign net flow.

        Args:
            candles: List of candles (used for date alignment)
            period: Rolling window size in days

        Returns:
            List of foreign net flow values, aligned to candles.
            Returns 0 for dates without broker data.
        """
        if not candles or period < 1:
            return []

        result: list[Decimal] = []

        for i, candle in enumerate(candles):
            # Calculate rolling sum over the period
            flow_sum = Decimal("0")
            count = 0

            for j in range(max(0, i - period + 1), i + 1):
                candle_date = candles[j].date
                if candle_date in self._broker_summaries:
                    summary = self._broker_summaries[candle_date]
                    flow_sum += summary.foreign_net_value
                    count += 1

            # Only emit value if we have at least one data point
            # This handles sparse broker data gracefully
            result.append(flow_sum)

        return result


class ForeignFlowRatioIndicator(IndicatorPlugin):
    """
    Foreign flow ratio indicator.

    Computes foreign net flow as percentage of total trading value.
    Range: -100% to +100%

    Positive = foreign net buying
    Negative = foreign net selling
    """

    name = "FOREIGN_FLOW_RATIO"
    default_period = 1

    def __init__(self) -> None:
        """Initialize indicator."""
        self._broker_summaries: dict[date, BrokerSummary] = {}

    def set_broker_data(self, summaries: list[BrokerSummary]) -> None:
        """Set broker summary data for indicator computation."""
        self._broker_summaries = {s.date: s for s in summaries}

    def compute(
        self,
        candles: list[Candle],
        period: int,
    ) -> list[Decimal]:
        """
        Compute rolling average foreign flow ratio.

        Args:
            candles: List of candles (used for date alignment)
            period: Rolling window size in days

        Returns:
            List of foreign flow ratio values (percentage).
        """
        if not candles or period < 1:
            return []

        result: list[Decimal] = []

        for i, candle in enumerate(candles):
            # Calculate rolling average ratio over the period
            ratio_sum = Decimal("0")
            count = 0

            for j in range(max(0, i - period + 1), i + 1):
                candle_date = candles[j].date
                if candle_date in self._broker_summaries:
                    summary = self._broker_summaries[candle_date]
                    ratio_sum += summary.foreign_flow_ratio
                    count += 1

            # Average ratio over the period
            if count > 0:
                result.append(ratio_sum / count)
            else:
                result.append(Decimal("0"))

        return result


class ConsecutiveForeignBuyIndicator(IndicatorPlugin):
    """
    Consecutive foreign buy days indicator.

    Counts consecutive days of foreign net buying.
    Resets to 0 when foreign becomes net seller.

    Useful for detecting sustained accumulation patterns.

    Example in rules:
        when:
          left:
            indicator: consecutive_foreign_buy
          operator: ">="
          right:
            value: 3  # 3+ consecutive days of foreign buying
    """

    name = "CONSECUTIVE_FOREIGN_BUY"
    default_period = 1  # Not used, but required

    def __init__(self) -> None:
        """Initialize indicator."""
        self._broker_summaries: dict[date, BrokerSummary] = {}

    def set_broker_data(self, summaries: list[BrokerSummary]) -> None:
        """Set broker summary data for indicator computation."""
        self._broker_summaries = {s.date: s for s in summaries}

    def compute(
        self,
        candles: list[Candle],
        period: int,
    ) -> list[Decimal]:
        """
        Compute consecutive foreign buying days.

        Args:
            candles: List of candles (used for date alignment)
            period: Not used for this indicator

        Returns:
            List of consecutive buy day counts.
        """
        if not candles:
            return []

        result: list[Decimal] = []
        consecutive_count = 0

        for candle in candles:
            if candle.date in self._broker_summaries:
                summary = self._broker_summaries[candle.date]
                if summary.is_foreign_accumulating:
                    consecutive_count += 1
                else:
                    consecutive_count = 0
            # If no broker data, maintain current count (no change)

            result.append(Decimal(consecutive_count))

        return result
