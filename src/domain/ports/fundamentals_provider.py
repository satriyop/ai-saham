"""
Port: FundamentalsProvider

Provides key fundamental ratios for a ticker (P/E, ROE, Piotroski F-Score, etc.)
sourced from Stockbit KeyStats.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod

from src.domain.value_objects.company_fundamentals import CompanyFundamentals


class FundamentalsProvider(ABC):
    """Abstract source for per-ticker fundamental ratios."""

    @abstractmethod
    def get_fundamentals(self, ticker: str) -> CompanyFundamentals | None:
        """Return fundamental ratios for ticker.

        Returns:
            CompanyFundamentals, or None if data unavailable.
            Never raises.
        """
        ...
