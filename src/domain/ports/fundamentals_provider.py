"""
Port: FundamentalsProvider

Provides key fundamental ratios for a ticker (P/E, ROE, Piotroski F-Score, etc.)
sourced from Stockbit KeyStats.

Layer: Domain (port definition)
"""

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.company_fundamentals import CompanyFundamentals


class FundamentalsProvider(ABC):
    """Abstract source for per-ticker fundamental ratios."""

    @abstractmethod
    def get_fundamentals(
        self,
        ticker: str,
        as_of_date: date | None = None,
    ) -> CompanyFundamentals | None:
        """Return fundamental ratios for ticker.

        Args:
            ticker: Stock ticker symbol.
            as_of_date: When provided, only return data that was available at
                this historical date (prevents look-ahead bias in backtests).
                None means live mode — apply normal TTL-based staleness check.

        Returns:
            CompanyFundamentals, or None if data unavailable.
            Never raises.
        """
        ...
