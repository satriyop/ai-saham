"""
Port: AnalystConsensusProvider

Provides aggregated analyst buy/hold/sell ratings and price target for a ticker.
Implementations source data from Stockbit.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.analyst_consensus import AnalystConsensus


class AnalystConsensusProvider(ABC):
    """Abstract source for analyst consensus rating data."""

    @abstractmethod
    def get_consensus(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> AnalystConsensus | None:
        """Return analyst consensus for ticker.

        Args:
            ticker: Stock ticker symbol.
            as_of_date: When provided, only return a snapshot fetched on or
                before this historical date. None means current/live behavior.

        Returns:
            AnalystConsensus object, or None if data unavailable.
            Never raises.
        """
        ...
