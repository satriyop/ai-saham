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
from datetime import date


@dataclass(frozen=True)
class ShareholdingComposition:
    ticker: str
    report_date: date | None
    institution_pct: float         # sum of institutional category holders
    individual_pct: float          # "Individual" retail category
    top_holder_name: str           # largest single named entity (not a category)
    top_holder_pct: float          # its ownership %

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
        return {
            "report_date": self.report_date.isoformat() if self.report_date else None,
            "institution_pct": round(self.institution_pct, 2),
            "individual_pct": round(self.individual_pct, 2),
            "top_holder_name": self.top_holder_name,
            "top_holder_pct": round(self.top_holder_pct, 2),
        }
