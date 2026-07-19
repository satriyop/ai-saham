"""
ForeignFlowScoreBreakdown value object.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


FOREIGN_FLOW_COMPONENT_KEYS = frozenset(
    {"cons", "streak", "vwap", "rsi", "flow", "bb", "inst"}
)
INSTITUTIONAL_FLOW_COMPONENT_KEYS = frozenset(
    {"cons", "streak", "vwap", "flow", "inst"}
)


class ForeignFlowComponentStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class ForeignFlowComponentScore:
    """One scored foreign-flow component with explicit availability status."""

    key: str
    score_points: float | None
    max_points: float
    status: ForeignFlowComponentStatus

    def __post_init__(self) -> None:
        if self.max_points < 0:
            raise ValueError(
                f"ForeignFlowComponentScore max_points must be >= 0, got {self.max_points}"
            )
        if not isinstance(self.status, ForeignFlowComponentStatus):
            raise ValueError(
                f"ForeignFlowComponentScore status must be ForeignFlowComponentStatus, "
                f"got {self.status!r}"
            )
        if self.status is ForeignFlowComponentStatus.AVAILABLE:
            if self.max_points <= 0:
                raise ValueError(
                    "AVAILABLE ForeignFlowComponentScore requires max_points > 0"
                )
            if self.score_points is None:
                raise ValueError(
                    "AVAILABLE ForeignFlowComponentScore requires numeric score_points"
                )
            if not (0.0 <= self.score_points <= self.max_points):
                raise ValueError(
                    f"AVAILABLE ForeignFlowComponentScore score_points must be "
                    f"0.0–{self.max_points:g}, got {self.score_points}"
                )
        else:
            if self.status is ForeignFlowComponentStatus.MISSING and self.max_points <= 0:
                raise ValueError(
                    "MISSING ForeignFlowComponentScore requires max_points > 0"
                )
            if self.score_points is not None:
                raise ValueError(
                    f"{self.status.value} ForeignFlowComponentScore requires "
                    f"score_points is None, got {self.score_points}"
                )

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "score_points": (
                round(self.score_points, 1) if self.score_points is not None else None
            ),
            "max_points": self.max_points,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ForeignFlowComponentScore":
        return cls(
            key=str(data["key"]),
            score_points=(
                float(data["score_points"])
                if data.get("score_points") is not None
                else None
            ),
            max_points=float(data["max_points"]),
            status=ForeignFlowComponentStatus(str(data["status"])),
        )


@dataclass(frozen=True)
class ForeignFlowScoreBreakdown:
    """Deterministic score components for foreign broker-flow evidence."""

    ticker: str
    snapshot_date: date
    components: tuple[ForeignFlowComponentScore, ...] = field(default_factory=tuple)
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
        keys = [c.key for c in self.components]
        if len(keys) != len(set(keys)):
            raise ValueError(
                f"ForeignFlowScoreBreakdown component keys must be unique, got {keys}"
            )
        if set(keys) != FOREIGN_FLOW_COMPONENT_KEYS:
            missing = sorted(FOREIGN_FLOW_COMPONENT_KEYS - set(keys))
            unexpected = sorted(set(keys) - FOREIGN_FLOW_COMPONENT_KEYS)
            raise ValueError(
                "ForeignFlowScoreBreakdown requires exactly the canonical component "
                f"keys; missing={missing}, unexpected={unexpected}"
            )
        if self.component("cons").status is ForeignFlowComponentStatus.MISSING:
            raise ValueError("cons cannot be MISSING for a scored candidate")
        if self.component("streak").status is ForeignFlowComponentStatus.MISSING:
            raise ValueError("streak cannot be MISSING for a scored candidate")
        _validate_optional_component(self.component("vwap"), self.vwap_discount_pct)
        _validate_optional_component(self.component("rsi"), self.rsi)
        _validate_optional_component(self.component("flow"), self.avg_flow_ratio)
        _validate_optional_component(self.component("bb"), self.bb_width_pctile)
        _validate_optional_component(self.component("inst"), self.bci_label)

    @property
    def foreign_flow_score(self) -> float:
        """Canonical score derived from the typed component records."""
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
    def enabled_max_points(self) -> float:
        return sum(
            c.max_points
            for c in self.components
            if c.status is not ForeignFlowComponentStatus.DISABLED
        )

    @property
    def available_max_points(self) -> float:
        return sum(
            c.max_points
            for c in self.components
            if c.status is ForeignFlowComponentStatus.AVAILABLE
        )

    @property
    def component_coverage(self) -> float:
        enabled = self.enabled_max_points
        if enabled <= 0:
            return 0.0
        return min(1.0, self.available_max_points / enabled)

    @property
    def missing_components(self) -> tuple[str, ...]:
        return tuple(
            c.key
            for c in self.components
            if c.status is ForeignFlowComponentStatus.MISSING
        )

    @property
    def breakdown_dict(self) -> dict[str, float | None]:
        """Points by key; MISSING/DISABLED map to None (not zero)."""
        return {c.key: c.score_points for c in self.components}

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "foreign_flow_score": self.foreign_flow_score,
            "max_score": self.max_score,
            "score_unit": "points_0_100",
            "component_coverage": round(self.component_coverage, 4),
            "component_coverage_unit": "ratio_0_1",
            "missing_components": list(self.missing_components),
            "aggregation": (
                "capped_sum_of_available_component_points; "
                "missing and disabled contribute no points and are excluded "
                "from available_max_points; coverage = available_max / enabled_max"
            ),
            "components": [c.to_dict() for c in self.components],
            "breakdown": {
                key: (round(value, 1) if value is not None else None)
                for key, value in self.breakdown_dict.items()
            },
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


def _validate_optional_component(
    component: ForeignFlowComponentScore,
    raw_value: object | None,
) -> None:
    if component.status is ForeignFlowComponentStatus.DISABLED:
        return
    expected = (
        ForeignFlowComponentStatus.MISSING
        if raw_value is None
        else ForeignFlowComponentStatus.AVAILABLE
    )
    if component.status is not expected:
        raise ValueError(
            f"component {component.key!r} status {component.status.value} conflicts "
            f"with raw input {'missing' if raw_value is None else 'available'}"
        )
