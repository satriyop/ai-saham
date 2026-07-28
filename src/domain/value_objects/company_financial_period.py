"""
CompanyFinancialPeriod — one period of multi-period financial statement data.

Distinct from CompanyFundamentals (Stockbit keystats ratios / quality screen).
Holds a sparse row for one statement_kind (income | balance | cashflow) so
sources never mix silently and kinds never share a PK slot.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

FinancialPeriodType = Literal["quarter", "annual"]
FinancialStatementKind = Literal["income", "balance", "cashflow"]

ALL_STATEMENT_KINDS: frozenset[FinancialStatementKind] = frozenset(
    ("income", "balance", "cashflow")
)

_INCOME_FIELDS = (
    "total_revenue",
    "net_income",
    "net_income_incl_nci",
    "interest_income",
    "operating_income",
    "eps_basic",
    "eps_diluted",
)
_BALANCE_FIELDS = (
    "total_assets",
    "total_liabilities",
    "stockholders_equity",
    "cash_and_equivalents",
    "total_debt",
)
_CASHFLOW_FIELDS = (
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "free_cash_flow",
    "capital_expenditure",
    "end_cash_position",
)


def fields_for(statement_kind: FinancialStatementKind) -> tuple[str, ...]:
    """Metric field names meaningful for a statement kind (display/tests)."""
    if statement_kind == "income":
        return _INCOME_FIELDS
    if statement_kind == "balance":
        return _BALANCE_FIELDS
    if statement_kind == "cashflow":
        return _CASHFLOW_FIELDS
    raise ValueError(f"unknown statement_kind: {statement_kind!r}")


@dataclass(frozen=True)
class CompanyFinancialPeriod:
    """One ticker × statement_kind × period_end × period_type × source snapshot."""

    ticker: str
    period_end: date
    period_type: FinancialPeriodType
    statement_kind: FinancialStatementKind
    source: str
    currency: str | None
    # Income
    total_revenue: int | None
    net_income: int | None
    net_income_incl_nci: int | None
    interest_income: int | None
    operating_income: int | None
    eps_basic: float | None
    eps_diluted: float | None
    # Balance
    total_assets: int | None
    total_liabilities: int | None
    stockholders_equity: int | None
    cash_and_equivalents: int | None
    total_debt: int | None
    # Cash flow
    operating_cash_flow: int | None
    investing_cash_flow: int | None
    financing_cash_flow: int | None
    free_cash_flow: int | None
    capital_expenditure: int | None
    end_cash_position: int | None
    fetched_at: datetime

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "period_end": self.period_end.isoformat(),
            "period_type": self.period_type,
            "statement_kind": self.statement_kind,
            "source": self.source,
            "currency": self.currency,
            "total_revenue": self.total_revenue,
            "net_income": self.net_income,
            "net_income_incl_nci": self.net_income_incl_nci,
            "interest_income": self.interest_income,
            "operating_income": self.operating_income,
            "eps_basic": self.eps_basic,
            "eps_diluted": self.eps_diluted,
            "total_assets": self.total_assets,
            "total_liabilities": self.total_liabilities,
            "stockholders_equity": self.stockholders_equity,
            "cash_and_equivalents": self.cash_and_equivalents,
            "total_debt": self.total_debt,
            "operating_cash_flow": self.operating_cash_flow,
            "investing_cash_flow": self.investing_cash_flow,
            "financing_cash_flow": self.financing_cash_flow,
            "free_cash_flow": self.free_cash_flow,
            "capital_expenditure": self.capital_expenditure,
            "end_cash_position": self.end_cash_position,
            "fetched_at": self.fetched_at.isoformat(),
        }

    def has_any_metric(self) -> bool:
        """True when at least one metric for this statement_kind is non-null."""
        for name in fields_for(self.statement_kind):
            if getattr(self, name) is not None:
                return True
        return False
