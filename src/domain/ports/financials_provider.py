"""
Port: FinancialsProvider — multi-period financial statements from an external source.

Layer: Domain (port definition)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.company_financial_period import CompanyFinancialPeriod


class FinancialsProvider(ABC):
    """Abstract source for multi-period income-statement periods."""

    @abstractmethod
    def fetch_statements(
        self,
        ticker: str,
        *,
        include_quarterly: bool = True,
        include_annual: bool = True,
    ) -> list[CompanyFinancialPeriod]:
        """Fetch statement periods for ticker.

        Args:
            ticker: IDX ticker without market suffix (e.g. ``BBCA``).
            include_quarterly: Include quarterly periods when available.
            include_annual: Include annual periods when available.

        Returns:
            List of periods (may be empty). Never raises for missing data;
            infrastructure may raise only on hard transport failures if
            documented — prefer empty list + use-case error mapping.
        """
        ...
