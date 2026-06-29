"""
ForeignFlowEvidence value object.

Layer: Domain
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from src.domain.value_objects.foreign_flow_score_breakdown import ForeignFlowScoreBreakdown


COMPOSITE_FOREIGN_FLOW = "composite_foreign_flow"


@dataclass(frozen=True)
class ForeignFlowEvidence:
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
    longer_term_context: tuple[tuple[str, object], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if isinstance(self.longer_term_context, Mapping):
            object.__setattr__(
                self,
                "longer_term_context",
                tuple(
                    sorted(
                        (str(key), _freeze_context_value(value))
                        for key, value in self.longer_term_context.items()
                    )
                ),
            )
        elif not isinstance(self.longer_term_context, tuple):
            object.__setattr__(
                self,
                "longer_term_context",
                tuple(
                    (str(key), _freeze_context_value(value))
                    for key, value in self.longer_term_context
                ),
            )
        if self.max_score <= 0:
            raise ValueError("ForeignFlowEvidence max_score must be positive")
        if not 0 <= self.composite_score <= self.max_score:
            raise ValueError(
                f"ForeignFlowEvidence composite_score must be 0-{self.max_score:g}, "
                f"got {self.composite_score}"
            )
        if self.total_days < 0:
            raise ValueError("ForeignFlowEvidence total_days cannot be negative")
        if self.net_buy_days < 0:
            raise ValueError("ForeignFlowEvidence net_buy_days cannot be negative")
        if self.net_buy_days > self.total_days:
            raise ValueError("ForeignFlowEvidence net_buy_days cannot exceed total_days")

    @property
    def component_breakdown_dict(self) -> dict[str, float]:
        return dict(self.component_breakdown)

    @property
    def longer_term_context_dict(self) -> dict[str, object]:
        return {
            key: _thaw_context_value(value)
            for key, value in self.longer_term_context
        }

    @classmethod
    def from_score_breakdown(
        cls,
        breakdown: ForeignFlowScoreBreakdown,
        *,
        net_buy_days: int,
        total_days: int,
        streak: int | None = None,
        vwap_pct: float | None = None,
        longer_term_context: dict[str, object] | None = None,
    ) -> "ForeignFlowEvidence":
        flow_direction = classify_flow_direction(breakdown.avg_flow_ratio)
        return cls(
            composite_score=breakdown.foreign_flow_score,
            max_score=breakdown.max_score,
            score_family=COMPOSITE_FOREIGN_FLOW,
            flow_direction=flow_direction,
            confirmation_status=classify_confirmation_status(
                composite_score=breakdown.foreign_flow_score,
                max_score=breakdown.max_score,
                flow_direction=flow_direction,
            ),
            net_buy_days=net_buy_days,
            total_days=total_days,
            streak=breakdown.consecutive_streak if streak is None else streak,
            avg_flow_ratio=breakdown.avg_flow_ratio,
            f_vwap_pct=breakdown.vwap_discount_pct,
            vwap_pct=vwap_pct,
            bb_width_pctile=breakdown.bb_width_pctile,
            component_breakdown=breakdown.breakdown,
            longer_term_context=tuple(
                sorted(
                    (str(key), _freeze_context_value(value))
                    for key, value in (longer_term_context or {}).items()
                )
            ),
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
            "longer_term_context": self.longer_term_context_dict,
        }


def classify_flow_direction(avg_flow_ratio: float | None) -> str:
    if avg_flow_ratio is None:
        return "UNKNOWN"
    if avg_flow_ratio > 0:
        return "POSITIVE"
    if avg_flow_ratio < 0:
        return "NEGATIVE"
    return "FLAT"


def _freeze_context_value(value: object) -> object:
    if isinstance(value, Mapping):
        return tuple(
            sorted(
                (str(key), _freeze_context_value(item))
                for key, item in value.items()
            )
        )
    if isinstance(value, tuple):
        return tuple(_freeze_context_value(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_context_value(item) for item in value)
    return value


def _thaw_context_value(value: object) -> object:
    if isinstance(value, tuple):
        if all(
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[0], str)
            for item in value
        ):
            return {key: _thaw_context_value(item) for key, item in value}
        return [_thaw_context_value(item) for item in value]
    return value


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
