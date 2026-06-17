"""
Port: AnalystConsensusProvider

Provides aggregated analyst buy/hold/sell ratings and price target for a ticker.
Implementations source data from Stockbit.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.analyst_consensus import AnalystConsensus


class AnalystConsensusProvider(ABC):
    """Abstract source for analyst consensus rating data."""

    @abstractmethod
    def get_consensus(self, ticker: str) -> AnalystConsensus | None:
        """Return analyst consensus for ticker.

        Returns:
            AnalystConsensus object, or None if data unavailable.
            Never raises.
        """
        ...
