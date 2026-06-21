"""
BrokerDistributionProvider port — cross-broker counterparty flow.

Layer: Domain
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.broker_distribution import BrokerDistributionSnapshot


class BrokerDistributionProvider(ABC):
    @abstractmethod
    def get_distribution(
        self,
        ticker: str,
        trading_date: date | None = None,
    ) -> "BrokerDistributionSnapshot | None":
        """Return the broker distribution snapshot for ticker on trading_date.

        Args:
            ticker:       IDX ticker symbol.
            trading_date: Date to fetch; None = today (latest available).

        Returns:
            BrokerDistributionSnapshot, or None if data unavailable.
        """

    @abstractmethod
    def is_cache_fresh(self, ticker: str) -> bool:
        """True when today's distribution is already cached."""
