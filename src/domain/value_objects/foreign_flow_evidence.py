"""
ForeignFlowEvidence value object.

Layer: Domain
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from src.domain.value_objects.accum_score_breakdown import (
    FOREIGN_FLOW_COMPONENT_KEYS,
    AccumScoreBreakdown,
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
)

COMPOSITE_FOREIGN_FLOW = "composite_foreign_flow"


@dataclass(frozen=True)
class ForeignFlowEvidence:
    """Explicit foreign-flow evidence contract used by swing workflows."""

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
    components: tuple[ForeignFlowComponentScore, ...] = field(default_factory=tuple)
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
        if self.total_days < 0:
            raise ValueError("ForeignFlowEvidence total_days cannot be negative")
        if self.net_buy_days < 0:
            raise ValueError("ForeignFlowEvidence net_buy_days cannot be negative")
        if self.net_buy_days > self.total_days:
            raise ValueError("ForeignFlowEvidence net_buy_days cannot exceed total_days")
        keys = [c.key for c in self.components]
        if len(keys) != len(set(keys)):
            raise ValueError(f"ForeignFlowEvidence component keys must be unique, got {keys}")
        if set(keys) != FOREIGN_FLOW_COMPONENT_KEYS:
            missing = sorted(FOREIGN_FLOW_COMPONENT_KEYS - set(keys))
            unexpected = sorted(set(keys) - FOREIGN_FLOW_COMPONENT_KEYS)
            raise ValueError(
                "ForeignFlowEvidence requires exactly the canonical component keys; "
                f"missing={missing}, unexpected={unexpected}"
            )

    @property
    def accum_score(self) -> float:
        return round(
            min(
                sum(
                    component.score_points
                    for component in self.components
                    if component.status is ForeignFlowComponentStatus.AVAILABLE
                    and component.score_points is not None
                ),
                self.max_score,
            ),
            1,
        )

    def component(self, key: str) -> ForeignFlowComponentScore | None:
        for component in self.components:
            if component.key == key:
                return component
        return None

    @property
    def components_by_key(self) -> dict[str, ForeignFlowComponentScore]:
        return {c.key: c for c in self.components}

    @property
    def component_coverage(self) -> float:
        enabled = sum(
            c.max_points
            for c in self.components
            if c.status is not ForeignFlowComponentStatus.DISABLED
        )
        if enabled <= 0:
            return 0.0
        available = sum(
            c.max_points
            for c in self.components
            if c.status is ForeignFlowComponentStatus.AVAILABLE
        )
        return min(1.0, available / enabled)

    @property
    def missing_components(self) -> tuple[str, ...]:
        return tuple(
            c.key for c in self.components if c.status is ForeignFlowComponentStatus.MISSING
        )

    @property
    def longer_term_context_dict(self) -> dict[str, object]:
        return {key: _thaw_context_value(value) for key, value in self.longer_term_context}

    @classmethod
    def from_score_breakdown(
        cls,
        breakdown: AccumScoreBreakdown,
        *,
        net_buy_days: int,
        total_days: int,
        streak: int | None = None,
        vwap_pct: float | None = None,
        longer_term_context: dict[str, object] | None = None,
    ) -> "ForeignFlowEvidence":
        flow_direction = classify_flow_direction(breakdown.avg_flow_ratio)
        return cls(
            max_score=breakdown.max_score,
            score_family=COMPOSITE_FOREIGN_FLOW,
            flow_direction=flow_direction,
            confirmation_status=classify_confirmation_status(
                accum_score=breakdown.accum_score,
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
            components=breakdown.components,
            longer_term_context=tuple(
                sorted(
                    (str(key), _freeze_context_value(value))
                    for key, value in (longer_term_context or {}).items()
                )
            ),
        )

    def to_dict(self) -> dict:
        return {
            "accum_score": self.accum_score,
            "max_score": self.max_score,
            "score_family": self.score_family,
            "flow_direction": self.flow_direction,
            "confirmation_status": self.confirmation_status,
            "net_buy_days": self.net_buy_days,
            "total_days": self.total_days,
            "streak": self.streak,
            "avg_flow_ratio": (
                round(self.avg_flow_ratio, 2) if self.avg_flow_ratio is not None else None
            ),
            "f_vwap_pct": round(self.f_vwap_pct, 2) if self.f_vwap_pct is not None else None,
            "vwap_pct": round(self.vwap_pct, 2) if self.vwap_pct is not None else None,
            "bb_width_pctile": (
                round(self.bb_width_pctile, 3) if self.bb_width_pctile is not None else None
            ),
            "component_coverage": round(self.component_coverage, 4),
            "component_coverage_unit": "ratio_0_1",
            "missing_components": list(self.missing_components),
            "score_unit": "points_0_100",
            "components": [c.to_dict() for c in self.components],
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
        return tuple(sorted((str(key), _freeze_context_value(item)) for key, item in value.items()))
    if isinstance(value, tuple):
        return tuple(_freeze_context_value(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze_context_value(item) for item in value)
    return value


def _thaw_context_value(value: object) -> object:
    if isinstance(value, tuple):
        if all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        ):
            return {key: _thaw_context_value(item) for key, item in value}
        return [_thaw_context_value(item) for item in value]
    return value


def classify_confirmation_status(
    *,
    accum_score: float,
    max_score: float,
    flow_direction: str,
) -> str:
    score_ratio = accum_score / max_score
    if flow_direction == "POSITIVE" and score_ratio >= (58.3 / 100.0):
        return "CONFIRMED"
    if score_ratio >= (33.3 / 100.0):
        return "WATCH_ZONE"
    return "WEAK"
