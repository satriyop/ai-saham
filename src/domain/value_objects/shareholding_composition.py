"""
ShareholdingComposition value object.

Holds aggregated shareholding structure for a ticker:
- institution_pct: sum of all known institutional categories (funds, banks, etc.)
- individual_pct: retail individual shareholders
- top_holder_name / top_holder_pct: largest single named entity holder

Sourced from Stockbit /insider/shareholding/composition/companies/{ticker}.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class ShareholdingComposition:
    ticker: str
    report_date: date | None
    institution_pct: float  # sum of institutional category holders
    individual_pct: float  # "Individual" retail category
    top_holder_name: str  # largest single named entity (not a category)
    top_holder_pct: float  # its ownership %
    total_shares: int | None = None  # periods[0].total_shares.raw (total issued shares)
    total_shares_formatted: str | None = None  # e.g. "123.28 B"
    fetched_at: datetime | None = None

    @property
    def free_float_pct(self) -> float:
        """Estimated publicly tradable float: individual_pct + institution_pct. Clamped [0, 100]."""
        return round(min(max(self.individual_pct + self.institution_pct, 0.0), 100.0), 2)

    @property
    def is_institutionally_held(self) -> bool:
        return self.institution_pct >= 30.0

    @property
    def label(self) -> str:
        holder_short = self.top_holder_name[:20].strip()
        parts = []
        if self.top_holder_pct > 0:
            parts.append(f"{holder_short} {self.top_holder_pct:.1f}%")
        if self.institution_pct > 0:
            parts.append(f"Inst {self.institution_pct:.1f}%")
        if self.individual_pct > 0:
            parts.append(f"Individual {self.individual_pct:.1f}%")
        return " | ".join(parts) if parts else "N/A"

    def to_dict(self) -> dict:
        d = {
            "report_date": self.report_date.isoformat() if self.report_date else None,
            "institution_pct": round(self.institution_pct, 2),
            "individual_pct": round(self.individual_pct, 2),
            "top_holder_name": self.top_holder_name,
            "top_holder_pct": round(self.top_holder_pct, 2),
        }
        if self.total_shares is not None:
            d["total_shares"] = self.total_shares
        if self.total_shares_formatted is not None:
            d["total_shares_formatted"] = self.total_shares_formatted
        if self.fetched_at is not None:
            d["fetched_at"] = self.fetched_at.isoformat()
        return d
