"""
Port: ShareholdingProvider

Provides shareholding composition (institutional %, individual %, top holder)
for a ticker based on IDX filing disclosures.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.shareholding_composition import ShareholdingComposition


class ShareholdingProvider(ABC):
    """Abstract source for shareholding composition data."""

    @abstractmethod
    def get_composition(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> ShareholdingComposition | None:
        """Return shareholding composition for ticker.

        Args:
            ticker: Stock ticker symbol.
            as_of_date: When provided, only return data whose report_date (filing
                date) is on or before this historical date — prevents look-ahead
                bias in backtests. None means live mode (normal TTL check).

        Returns:
            ShareholdingComposition, or None if data unavailable.
            Never raises.
        """
        ...
