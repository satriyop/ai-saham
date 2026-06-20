"""
Port: RunningTradeChartProvider

Provides per-minute intraday price and broker flow chart for a ticker.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.running_trade_chart import RunningTradeChart


class RunningTradeChartProvider(ABC):
    """Abstract source for per-ticker intraday running trade chart."""

    @abstractmethod
    def fetch_chart(self, ticker: str) -> RunningTradeChart | None:
        """Return today's per-minute price + broker flow chart for ticker.

        Returns:
            RunningTradeChart, or None if data unavailable.
            Never raises. No caching — callers re-fetch for live data.
        """
        ...
