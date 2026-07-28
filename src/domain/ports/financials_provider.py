"""
Port: FinancialsProvider — multi-period financial statements from an external source.

Layer: Domain (port definition)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.company_financial_period import (
    CompanyFinancialPeriod,
    FinancialStatementKind,
)


class FinancialsProvider(ABC):
    """Abstract source for multi-period statement periods (income/BS/CF)."""

    @abstractmethod
    def fetch_statements(
        self,
        ticker: str,
        *,
        include_quarterly: bool = True,
        include_annual: bool = True,
        statement_kinds: frozenset[FinancialStatementKind],
    ) -> list[CompanyFinancialPeriod]:
        """Fetch statement periods for ticker.

        Args:
            ticker: IDX ticker without market suffix (e.g. ``BBCA``).
            include_quarterly: Include quarterly periods when available.
            include_annual: Include annual periods when available.
            statement_kinds: Which statement kinds to fetch (must be non-empty).

        Returns:
            List of periods (may be empty). Prefer empty list for missing
            frames per kind rather than failing the whole ticker.
        """
        ...
