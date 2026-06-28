"""
FlowEvidence value object.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass, field


COMPOSITE_FLOW_EVIDENCE = "composite_flow_evidence"


@dataclass(frozen=True)
class FlowEvidence:
    """Explicit foreign-flow evidence contract used by swing workflows."""

    composite_score: float
    max_score: float
    score_family: str
    flow_direction: str
    confirmation_status: str
    net_buy_days: int
    total_days: int
    streak: int
    avg_flow_ratio: float | None = None
    f_vwap_pct: float | None = None
    vwap_pct: float | None = None
    bb_width_pctile: float | None = None
    component_breakdown: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    longer_term_context: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_score <= 0:
            raise ValueError("FlowEvidence max_score must be positive")
        if not 0 <= self.composite_score <= self.max_score:
            raise ValueError(
                f"FlowEvidence composite_score must be 0-{self.max_score:g}, "
                f"got {self.composite_score}"
            )
        if self.total_days < 0:
            raise ValueError("FlowEvidence total_days cannot be negative")
        if self.net_buy_days < 0:
            raise ValueError("FlowEvidence net_buy_days cannot be negative")
        if self.net_buy_days > self.total_days:
            raise ValueError("FlowEvidence net_buy_days cannot exceed total_days")

    @property
    def component_breakdown_dict(self) -> dict[str, float]:
        return dict(self.component_breakdown)

    @classmethod
    def from_accumulation_evidence(
        cls,
        *,
        composite_score: float,
        max_score: float,
        net_buy_days: int,
        total_days: int,
        streak: int,
        avg_flow_ratio: float | None,
        f_vwap_pct: float | None,
        vwap_pct: float | None,
        bb_width_pctile: float | None,
        component_breakdown: tuple[tuple[str, float], ...],
        longer_term_context: dict[str, object] | None = None,
    ) -> "FlowEvidence":
        flow_direction = classify_flow_direction(avg_flow_ratio)
        return cls(
            composite_score=composite_score,
            max_score=max_score,
            score_family=COMPOSITE_FLOW_EVIDENCE,
            flow_direction=flow_direction,
            confirmation_status=classify_confirmation_status(
                composite_score=composite_score,
                max_score=max_score,
                flow_direction=flow_direction,
            ),
            net_buy_days=net_buy_days,
            total_days=total_days,
            streak=streak,
            avg_flow_ratio=avg_flow_ratio,
            f_vwap_pct=f_vwap_pct,
            vwap_pct=vwap_pct,
            bb_width_pctile=bb_width_pctile,
            component_breakdown=component_breakdown,
            longer_term_context=longer_term_context or {},
        )

    def to_dict(self) -> dict:
        return {
            "composite_score": self.composite_score,
            "max_score": self.max_score,
            "score_family": self.score_family,
            "flow_direction": self.flow_direction,
            "confirmation_status": self.confirmation_status,
            "net_buy_days": self.net_buy_days,
            "total_days": self.total_days,
            "streak": self.streak,
            "avg_flow_ratio": round(self.avg_flow_ratio, 2)
            if self.avg_flow_ratio is not None else None,
            "f_vwap_pct": round(self.f_vwap_pct, 2)
            if self.f_vwap_pct is not None else None,
            "vwap_pct": round(self.vwap_pct, 2)
            if self.vwap_pct is not None else None,
            "bb_width_pctile": round(self.bb_width_pctile, 3)
            if self.bb_width_pctile is not None else None,
            "component_breakdown": self.component_breakdown_dict,
            "longer_term_context": self.longer_term_context,
        }


def classify_flow_direction(avg_flow_ratio: float | None) -> str:
    if avg_flow_ratio is None:
        return "UNKNOWN"
    if avg_flow_ratio > 0:
        return "POSITIVE"
    if avg_flow_ratio < 0:
        return "NEGATIVE"
    return "FLAT"


def classify_confirmation_status(
    *,
    composite_score: float,
    max_score: float,
    flow_direction: str,
) -> str:
    score_ratio = composite_score / max_score
    if flow_direction == "POSITIVE" and score_ratio >= (70.0 / 120.0):
        return "CONFIRMED"
    if score_ratio >= (40.0 / 120.0):
        return "WATCH_ZONE"
    return "WEAK"
