"""
CompanyFundamentals value object.

Holds key fundamental ratios for a ticker sourced from Stockbit
/keystats/ratio/v1/{ticker}?year_limit=10.

Metrics are quarterly or TTM — they change when earnings are released,
not daily. Cached in SQLite with a 7-day TTL.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CompanyFundamentals:
    ticker: str
    pe_ratio_ttm: float | None  # Current PE Ratio (TTM)
    roe_ttm: float | None  # Return on Equity (TTM), in %
    net_profit_margin: float | None  # Net Profit Margin (Quarter), in %
    revenue_yoy_growth: float | None  # Revenue (Quarter YoY Growth), in %
    piotroski_f_score: int | None  # 0–9 (≥6 = healthy)
    dividend_yield: float | None  # Dividend Yield, in %
    week52_high: float | None
    week52_low: float | None
    near_52w_high_rank: float | None  # Rank (Near 52 Weeks High), 0–100 percentile
    market_cap_idr: int | None = None  # data.info.market_cap.raw (IDR)
    pbv: float | None = None  # data.info.pbv.raw
    fetched_at: datetime | None = None

    @property
    def is_quality(self) -> bool:
        """True when the stock passes basic fundamental quality gates."""
        roe_ok = self.roe_ttm is not None and self.roe_ttm >= 15.0
        f_ok = self.piotroski_f_score is None or self.piotroski_f_score >= 5
        margin_ok = self.net_profit_margin is None or self.net_profit_margin > 0
        return roe_ok and f_ok and margin_ok

    @property
    def label(self) -> str:
        parts = []
        if self.roe_ttm is not None:
            parts.append(f"ROE {self.roe_ttm:.1f}%")
        if self.net_profit_margin is not None:
            parts.append(f"NPM {self.net_profit_margin:.1f}%")
        if self.pe_ratio_ttm is not None:
            parts.append(f"PE {self.pe_ratio_ttm:.1f}")
        if self.revenue_yoy_growth is not None:
            sign = "+" if self.revenue_yoy_growth >= 0 else ""
            parts.append(f"Rev{sign}{self.revenue_yoy_growth:.1f}%")
        if self.piotroski_f_score is not None:
            parts.append(f"F={self.piotroski_f_score}")
        return " | ".join(parts) if parts else "N/A"

    def to_dict(self) -> dict:
        d = {
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "pe_ratio_ttm": self.pe_ratio_ttm,
            "roe_ttm": self.roe_ttm,
            "net_profit_margin": self.net_profit_margin,
            "revenue_yoy_growth": self.revenue_yoy_growth,
            "piotroski_f_score": self.piotroski_f_score,
            "dividend_yield": self.dividend_yield,
            "week52_high": self.week52_high,
            "week52_low": self.week52_low,
            "near_52w_high_rank": self.near_52w_high_rank,
            "is_quality": self.is_quality,
        }
        if self.market_cap_idr is not None:
            d["market_cap_idr"] = self.market_cap_idr
        if self.pbv is not None:
            d["pbv"] = self.pbv
        return d
