"""
UniverseSummaryProvider port - interface for building universe summaries.

Layer: Application
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.use_case.view_universe_summary_use_case import UniverseViewResult


class UniverseSummaryProvider(ABC):
    """Port interface for retrieving aggregated universe metrics without
    per-entity hydration overhead.
    """

    @abstractmethod
    def build_universe_view(
        self,
        universe_name: str,
        tickers: list[str],
        updated: str,
        as_of_date: date | None = None,
    ) -> "UniverseViewResult":
        """Build and populate UniverseViewResult for the specified universe and tickers.

        Args:
            universe_name: Name of the universe.
            tickers: Sorted list of tickers in the universe.
            updated: String indicating when the universe was last updated.
            as_of_date: Optional cutoff date for calculations.

        Returns:
            UniverseViewResult object.
        """
        pass
