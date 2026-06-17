"""
Port: ShareholdingProvider

Provides shareholding composition (institutional %, individual %, top holder)
for a ticker based on IDX filing disclosures.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.shareholding_composition import ShareholdingComposition


class ShareholdingProvider(ABC):
    """Abstract source for shareholding composition data."""

    @abstractmethod
    def get_composition(self, ticker: str) -> ShareholdingComposition | None:
        """Return shareholding composition for ticker.

        Returns:
            ShareholdingComposition, or None if data unavailable.
            Never raises.
        """
        ...
