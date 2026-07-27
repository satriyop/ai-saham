"""
View ticker financials — read multi-period statement rows from local cache.

Income statement is supported (yahoo cache via `saham fetch financials`).
Balance sheet and cash flow are accepted as filters but return an explicit
unsupported status until those statement kinds are persisted.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from src.domain.ports.financials_repository import FinancialsRepository
from src.domain.value_objects.company_financial_period import (
    CompanyFinancialPeriod,
    FinancialPeriodType,
)

FinancialStatementKind = Literal["income", "balance", "cashflow"]
FinancialsViewStatus = Literal["ok", "empty", "unsupported"]

_SUPPORTED_STATEMENTS: frozenset[str] = frozenset({"income"})


@dataclass(frozen=True)
class ViewTickerFinancialsRequest:
    ticker: str
    statement: FinancialStatementKind = "income"
    period_type: FinancialPeriodType = "quarter"
    limit: int = 8
    source: str | None = "yahoo"


@dataclass(frozen=True)
class ViewTickerFinancialsResult:
    ticker: str
    statement: FinancialStatementKind
    period_type: FinancialPeriodType
    source: str | None
    status: FinancialsViewStatus
    periods: tuple[CompanyFinancialPeriod, ...]
    message: str | None = None

    @property
    def fetch_hint(self) -> str:
        return f"saham fetch financials {self.ticker}"

    @property
    def as_of(self) -> date | None:
        if not self.periods:
            return None
        return self.periods[0].period_end


class ViewTickerFinancialsUseCase:
    """Read-only multi-period financials view for one ticker."""

    def __init__(self, repository: FinancialsRepository) -> None:
        self._repository = repository

    def execute(self, request: ViewTickerFinancialsRequest) -> ViewTickerFinancialsResult:
        ticker = request.ticker.upper().strip()
        statement = request.statement
        period_type = request.period_type
        limit = max(1, min(int(request.limit), 40))
        source = request.source

        if statement not in _SUPPORTED_STATEMENTS:
            return ViewTickerFinancialsResult(
                ticker=ticker,
                statement=statement,
                period_type=period_type,
                source=source,
                status="unsupported",
                periods=(),
                message=(
                    f"{statement} statement is not cached yet "
                    "(Phase A stores income only). "
                    f"Use --statement income after `{self._hint(ticker)}`."
                ),
            )

        rows = self._repository.list_for_ticker(
            ticker,
            period_type=period_type,
            source=source,
        )
        windowed = tuple(rows[:limit])
        if not windowed:
            return ViewTickerFinancialsResult(
                ticker=ticker,
                statement=statement,
                period_type=period_type,
                source=source,
                status="empty",
                periods=(),
                message=(
                    f"No {period_type} income periods cached for {ticker}. "
                    f"Run: {self._hint(ticker)}"
                ),
            )

        sources = {p.source for p in windowed}
        resolved_source = next(iter(sources)) if len(sources) == 1 else "mixed"
        return ViewTickerFinancialsResult(
            ticker=ticker,
            statement=statement,
            period_type=period_type,
            source=resolved_source,
            status="ok",
            periods=windowed,
        )

    @staticmethod
    def _hint(ticker: str) -> str:
        return f"saham fetch financials {ticker}"
