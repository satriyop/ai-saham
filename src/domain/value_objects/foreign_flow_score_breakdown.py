"""
ForeignFlowScoreBreakdown value object.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class ForeignFlowScoreBreakdown:
    """Deterministic score components for foreign broker-flow evidence."""

    ticker: str
    snapshot_date: date
    foreign_flow_score: float
    breakdown: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    max_score: float = 100.0
    net_buy_ratio: float = 0.0
    consecutive_streak: int = 0
    vwap_discount_pct: float | None = None
    rsi: float | None = None
    avg_flow_ratio: float | None = None
    bb_width_pctile: float | None = None
    bci_label: str | None = None
    bci_tier1_count: int = 0

    def __post_init__(self) -> None:
        if self.max_score <= 0:
            raise ValueError("ForeignFlowScoreBreakdown max_score must be positive")
        if not 0 <= self.foreign_flow_score <= self.max_score:
            raise ValueError(
                f"ForeignFlowScoreBreakdown foreign_flow_score must be 0-{self.max_score:g}, "
                f"got {self.foreign_flow_score}"
            )

    @property
    def breakdown_dict(self) -> dict[str, float]:
        return dict(self.breakdown)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "foreign_flow_score": self.foreign_flow_score,
            "max_score": self.max_score,
            "breakdown": self.breakdown_dict,
            "net_buy_ratio": round(self.net_buy_ratio, 4),
            "consecutive_streak": self.consecutive_streak,
            "vwap_discount_pct": round(self.vwap_discount_pct, 2)
            if self.vwap_discount_pct is not None
            else None,
            "rsi": round(self.rsi, 2) if self.rsi is not None else None,
            "avg_flow_ratio": round(self.avg_flow_ratio, 2)
            if self.avg_flow_ratio is not None
            else None,
            "bb_width_pctile": round(self.bb_width_pctile, 3)
            if self.bb_width_pctile is not None
            else None,
            "bci_label": self.bci_label,
            "bci_tier1_count": self.bci_tier1_count,
        }
