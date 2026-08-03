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

    @abstractmethod
    def get_history(
        self,
        ticker: str,
        limit: int,
        as_of_date: date | None = None,
    ) -> tuple[ShareholdingComposition, ...]:
        """Return up to `limit` distinct filing-period compositions, newest first.

        Args:
            ticker: Stock ticker symbol.
            limit: Maximum number of distinct periods to return.
            as_of_date: Same PIT semantics as get_composition — only periods on or
                before this historical date are eligible. Applied before dedupe
                and before limit. None means live mode.

        Returns:
            Tuple ordered newest period first, deduplicated to one row per
            filing period (re-fetches of the same period collapse to the latest
            fetch). Empty tuple if no eligible period exists. Never raises.
        """
        ...
