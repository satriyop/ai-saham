"""
SeasonalEdge — immutable value object for one ticker's monthly seasonality.

Represents the statistical edge for a specific calendar month derived from
N years of historical monthly returns (sourced from Stockbit seasonality API).

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SeasonalEdge:
    """Monthly seasonality statistics for a single ticker.

    Attributes:
        ticker:               IDX ticker symbol
        month:                Calendar month (1=Jan … 12=Dec)
        avg_monthly_return_pct: Average return in this month over back_years (e.g. +2.1 = +2.1%)
        win_rate_pct:         % of years this month was positive (e.g. 74.0 = 74%)
        positive_years:       Raw count: years with positive return in this month
        total_years:          Total years of history used
        back_years:           Number of years looked back when fetching
        source:               Data source tag (default "stockbit")
        fetched_at:           When this data was last retrieved from the API
    """

    ticker: str
    month: int  # 1–12
    avg_monthly_return_pct: float
    win_rate_pct: float  # 0–100
    positive_years: int
    total_years: int
    back_years: int
    source: str = "stockbit"
    fetched_at: datetime | None = None

    def __post_init__(self) -> None:
        """Validate seasonal statistics are internally consistent."""
        if not self.ticker:
            raise ValueError("Ticker cannot be empty")
        if not 1 <= self.month <= 12:
            raise ValueError("Month must be between 1 and 12")
        if not 0.0 <= self.win_rate_pct <= 100.0:
            raise ValueError("Win rate must be between 0 and 100")
        if self.positive_years < 0:
            raise ValueError("Positive years cannot be negative")
        if self.total_years <= 0:
            raise ValueError("Total years must be positive")
        if self.back_years <= 0:
            raise ValueError("Back years must be positive")
        if self.positive_years > self.total_years:
            raise ValueError("Positive years cannot exceed total years")

    @property
    def score(self) -> float:
        """Composite seasonal edge = avg_return × win_rate (both in same unit).

        Ranges roughly -100 to +100 when returns are expressed as pct.
        Used as tiebreaker in screener ranking — not a veto signal.

        Examples:
          avg_return=+2.1%, win_rate=74% → score = 2.1 * 0.74 = 1.55
          avg_return=-1.0%, win_rate=30% → score = -1.0 * 0.30 = -0.30
        """
        return self.avg_monthly_return_pct * (self.win_rate_pct / 100.0)

    @property
    def label(self) -> str:
        """Human-readable summary, e.g. '+2.1% (74%wr, 5y)'."""
        sign = "+" if self.avg_monthly_return_pct >= 0 else ""
        return (
            f"{sign}{self.avg_monthly_return_pct:.1f}%"
            f" ({self.win_rate_pct:.0f}%wr, {self.total_years}y)"
        )

    @property
    def is_tailwind(self) -> bool:
        """True when both avg return is positive and win-rate exceeds 50%."""
        return self.avg_monthly_return_pct > 0 and self.win_rate_pct > 50.0

    @property
    def is_headwind(self) -> bool:
        """True when avg return is negative and win-rate is below 50%."""
        return self.avg_monthly_return_pct < 0 and self.win_rate_pct < 50.0
