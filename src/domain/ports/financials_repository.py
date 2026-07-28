"""
Port: FinancialsRepository — persistence for multi-period financial statements.

Layer: Domain (port definition)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from src.domain.value_objects.company_financial_period import (
    CompanyFinancialPeriod,
    FinancialPeriodType,
    FinancialStatementKind,
)


class FinancialsRepository(ABC):
    """Store and query company financial statement periods."""

    @abstractmethod
    def upsert_many(self, periods: list[CompanyFinancialPeriod]) -> int:
        """Insert or replace periods. Returns number of rows written."""
        ...

    @abstractmethod
    def list_for_ticker(
        self,
        ticker: str,
        *,
        statement_kind: FinancialStatementKind | None = None,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> list[CompanyFinancialPeriod]:
        """Return periods for ticker, newest period_end first."""
        ...

    @abstractmethod
    def latest_period_end(
        self,
        ticker: str,
        *,
        statement_kind: FinancialStatementKind | None = None,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> date | None:
        """Most recent period_end stored for ticker (optional filters)."""
        ...

    @abstractmethod
    def needs_refresh(
        self,
        ticker: str,
        ttl_days: int,
        *,
        source: str,
        statement_kind: FinancialStatementKind,
    ) -> bool:
        """True when kind has no rows for source or last fetch is older than TTL."""
        ...
