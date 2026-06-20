"""
Port: IntradayBrokerChartProvider

Provides per-minute cumulative net flow for a broker's top stocks (broker-centric).

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.intraday_broker_chart import IntradayBrokerChart


class IntradayBrokerChartProvider(ABC):
    """Abstract source for per-broker intraday activity chart."""

    @abstractmethod
    def fetch_chart(self, broker_code: str) -> IntradayBrokerChart | None:
        """Return today's per-minute cumulative net flow for broker's top stocks.

        Args:
            broker_code: Broker identifier (e.g. "XL", "AK", "BK").

        Returns:
            IntradayBrokerChart, or None if data unavailable.
            Never raises. No caching — callers re-fetch for live data.
        """
        ...
