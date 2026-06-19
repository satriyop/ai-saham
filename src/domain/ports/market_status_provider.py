"""
Port: MarketStatusProvider

Returns the current IDX market status. Canonical implementation calls
Stockbit's /company-price-feed/market-time API. Fallback implementation
derives status from wall-clock time (offline-safe).

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.market_status import MarketStatus


class MarketStatusProvider(ABC):
    """Abstract source for current IDX market open/close status."""

    @abstractmethod
    def get_status(self) -> MarketStatus:
        """Return the current IDX market status.

        Never raises. Falls back gracefully on any error.
        """
        ...
