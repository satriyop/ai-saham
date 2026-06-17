"""
Port: OrderBookProvider

Provides a full order book snapshot for a ticker — total bid/offer depth,
live intraday foreign net, and pre-open IEP/IEV when available.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.order_book_snapshot import OrderBookSnapshot


class OrderBookProvider(ABC):
    """Abstract source for order book depth and live intraday flow."""

    @abstractmethod
    def fetch_snapshot(self, ticker: str) -> OrderBookSnapshot | None:
        """Return a full order book snapshot for ticker.

        Returns:
            OrderBookSnapshot, or None if data unavailable.
            Never raises.
        """
        ...
