"""
CompanyFinancialPeriod — one period of multi-period financial statement data.

Distinct from CompanyFundamentals (Stockbit keystats ratios / quality screen).
This VO holds income-statement line items for a single quarter or fiscal year,
with an explicit source so yfinance and future Stockbit rows never mix silently.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

FinancialPeriodType = Literal["quarter", "annual"]


@dataclass(frozen=True)
class CompanyFinancialPeriod:
    """One ticker × period_end × period_type × source financial snapshot."""

    ticker: str
    period_end: date
    period_type: FinancialPeriodType
    source: str
    currency: str | None
    total_revenue: int | None
    net_income: int | None
    net_income_incl_nci: int | None
    interest_income: int | None
    operating_income: int | None
    eps_basic: float | None
    eps_diluted: float | None
    fetched_at: datetime

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "period_end": self.period_end.isoformat(),
            "period_type": self.period_type,
            "source": self.source,
            "currency": self.currency,
            "total_revenue": self.total_revenue,
            "net_income": self.net_income,
            "net_income_incl_nci": self.net_income_incl_nci,
            "interest_income": self.interest_income,
            "operating_income": self.operating_income,
            "eps_basic": self.eps_basic,
            "eps_diluted": self.eps_diluted,
            "fetched_at": self.fetched_at.isoformat(),
        }
