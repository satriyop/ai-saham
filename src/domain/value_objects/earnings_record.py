"""
EarningsRecord — immutable value object for one quarter of earnings data.

Holds EPS actual vs. analyst consensus estimate, surprise direction, and
YoY comparison for a single ticker/quarter/year. Sourced from Stockbit
/earnings?keyword={ticker}&quarter={q}&year={y}.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EarningsRecord:
    """One quarter of earnings data for a ticker.

    Attributes:
        ticker:           IDX ticker symbol
        year:             Fiscal year (e.g. 2026)
        quarter:          Fiscal quarter 1–4
        eps_actual:       Reported EPS for the period (IDR per share)
        eps_estimate:     Analyst consensus EPS estimate before release (None if unavailable)
        eps_surprise_pct: (actual - estimate) / abs(estimate) * 100; positive = beat
        eps_yoy_change:   YoY change in EPS vs same quarter prior year (IDR)
        eps_prev_year:    EPS from same quarter prior year for context
        fetched_at:       When this record was last retrieved from the API
    """

    ticker: str
    year: int
    quarter: int       # 1–4
    eps_actual: float | None
    eps_estimate: float | None      # None when API returns "-"
    eps_surprise_pct: float | None  # None when no estimate
    eps_yoy_change: float | None    # signed IDR change vs prior year
    eps_prev_year: float | None
    fetched_at: datetime | None = None

    @property
    def period_label(self) -> str:
        return f"Q{self.quarter} {self.year}"

    @property
    def beat(self) -> bool | None:
        """True = beat estimate, False = miss, None = no estimate."""
        if self.eps_surprise_pct is None:
            return None
        return self.eps_surprise_pct > 0

    @property
    def yoy_growth_pct(self) -> float | None:
        """YoY EPS growth % vs same quarter prior year."""
        if self.eps_actual is None or self.eps_prev_year is None or self.eps_prev_year == 0:
            return None
        return (self.eps_actual - self.eps_prev_year) / abs(self.eps_prev_year) * 100

    @property
    def label(self) -> str:
        """Compact one-line summary, e.g. 'Q1 2026: EPS 119.1 (+3.8% YoY)'."""
        parts = [self.period_label]
        if self.eps_actual is not None:
            parts.append(f"EPS {self.eps_actual:.1f}")
        if self.yoy_growth_pct is not None:
            parts.append(f"({self.yoy_growth_pct:+.1f}% YoY)")
        if self.eps_surprise_pct is not None:
            parts.append(f"[{'BEAT' if self.beat else 'MISS'} {self.eps_surprise_pct:+.1f}%]")
        elif self.eps_estimate is None:
            parts.append("[no est.]")
        return " ".join(parts)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "year": self.year,
            "quarter": self.quarter,
            "period_label": self.period_label,
            "eps_actual": self.eps_actual,
            "eps_estimate": self.eps_estimate,
            "eps_surprise_pct": round(self.eps_surprise_pct, 2) if self.eps_surprise_pct is not None else None,
            "eps_yoy_change": self.eps_yoy_change,
            "eps_prev_year": self.eps_prev_year,
            "yoy_growth_pct": round(self.yoy_growth_pct, 1) if self.yoy_growth_pct is not None else None,
            "beat": self.beat,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }
