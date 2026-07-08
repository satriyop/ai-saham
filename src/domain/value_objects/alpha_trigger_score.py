"""Alpha/Trigger signal projection value objects.

Layer: Domain
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EvidenceAuthorityStatus(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    LOW_WEIGHT = "LOW_WEIGHT"
    PRODUCTION = "PRODUCTION"


@dataclass(frozen=True)
class EvidenceRegistration:
    evidence_name: str
    status: EvidenceAuthorityStatus
    low_weight_cap: float = 0.10
    promotion_requires: tuple[str, ...] = field(default_factory=tuple)
    promoted_by: str | None = None
    promoted_date: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_name:
            raise ValueError("evidence_name cannot be empty")
        if not isinstance(self.status, EvidenceAuthorityStatus):
            raise ValueError("status must be an EvidenceAuthorityStatus")
        _validate_unit("low_weight_cap", self.low_weight_cap)

    def effective_weight(self, configured_weight: float) -> float:
        if configured_weight < 0:
            raise ValueError("configured_weight must be >= 0")
        if self.status == EvidenceAuthorityStatus.DIAGNOSTIC:
            return 0.0
        if self.status == EvidenceAuthorityStatus.LOW_WEIGHT:
            return min(configured_weight, self.low_weight_cap)
        return configured_weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_name": self.evidence_name,
            "status": self.status.value,
            "low_weight_cap": self.low_weight_cap,
            "promotion_requires": list(self.promotion_requires),
            "promoted_by": self.promoted_by,
            "promoted_date": self.promoted_date,
        }


@dataclass(frozen=True)
class AlphaTriggerGroupContribution:
    group: str
    score: float
    configured_weight: float
    effective_weight: float
    alpha_fraction: float
    trigger_fraction: float
    alpha_weighted: float
    trigger_weighted: float
    evidence_status: EvidenceAuthorityStatus
    present: bool = True
    trigger_allowed: bool = True
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.group:
            raise ValueError("group cannot be empty")
        if self.present:
            _validate_score("score", self.score)
        elif self.score != 0.0:
            raise ValueError("missing group contributions must use score=0.0")
        if self.configured_weight < 0 or self.effective_weight < 0:
            raise ValueError("weights must be >= 0")
        _validate_unit("alpha_fraction", self.alpha_fraction)
        _validate_unit("trigger_fraction", self.trigger_fraction)
        if abs((self.alpha_fraction + self.trigger_fraction) - 1.0) > 1e-9:
            raise ValueError("alpha_fraction + trigger_fraction must equal 1.0")
        if self.alpha_weighted < 0 or self.trigger_weighted < 0:
            raise ValueError("weighted contributions must be >= 0")
        if not isinstance(self.evidence_status, EvidenceAuthorityStatus):
            raise ValueError("evidence_status must be an EvidenceAuthorityStatus")

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "score": round(self.score, 4),
            "configured_weight": round(self.configured_weight, 6),
            "effective_weight": round(self.effective_weight, 6),
            "alpha_fraction": round(self.alpha_fraction, 6),
            "trigger_fraction": round(self.trigger_fraction, 6),
            "alpha_weighted": round(self.alpha_weighted, 6),
            "trigger_weighted": round(self.trigger_weighted, 6),
            "evidence_status": self.evidence_status.value,
            "present": self.present,
            "trigger_allowed": self.trigger_allowed,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class AlphaTriggerScore:
    alpha_score: float | None
    trigger_score: float | None
    final_exact_score: float | None
    horizon: str
    alpha_weight: float
    group_contributions: tuple[AlphaTriggerGroupContribution, ...] = field(
        default_factory=tuple
    )
    coverage: float = 0.0           # legacy field name — use coverage_score property
    authority_coverage: float = 0.0  # legacy field name — use authority_coverage_score property
    conviction: float = 0.0          # legacy field name — use conviction_score property
    flow_trigger_allowed: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)
    unavailable_reasons: tuple[str, ...] = field(default_factory=tuple)

    # ── canonical name properties ──────────────────────────────────────────────
    @property
    def coverage_score(self) -> float:
        """Evidence completeness: fraction of alpha/trigger groups present."""
        return self.coverage

    @property
    def authority_coverage_score(self) -> float:
        """Post-registration coverage: fraction of groups allowed to affect production scoring."""
        return self.authority_coverage

    @property
    def conviction_score(self) -> float:
        """Directional strength: how strong the present evidence is."""
        return self.conviction

    def __post_init__(self) -> None:
        if not self.horizon:
            raise ValueError("horizon cannot be empty")
        _validate_unit("alpha_weight", self.alpha_weight)
        _validate_unit("coverage", self.coverage)
        _validate_unit("authority_coverage", self.authority_coverage)
        _validate_unit("conviction", self.conviction)
        for name, value in (
            ("alpha_score", self.alpha_score),
            ("trigger_score", self.trigger_score),
            ("final_exact_score", self.final_exact_score),
        ):
            if value is not None:
                _validate_score(name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha_score": _round_optional(self.alpha_score),
            "trigger_score": _round_optional(self.trigger_score),
            "final_exact_score": _round_optional(self.final_exact_score),
            "horizon": self.horizon,
            "alpha_weight": round(self.alpha_weight, 6),
            "trigger_weight": round(1.0 - self.alpha_weight, 6),
            "group_contributions": [c.to_dict() for c in self.group_contributions],
            "coverage_score": round(self.coverage, 4),         # canonical
            "authority_coverage_score": round(self.authority_coverage, 4),  # canonical
            "conviction_score": round(self.conviction, 4),      # canonical
            "coverage": round(self.coverage, 4),                # legacy alias
            "authority_coverage": round(self.authority_coverage, 4),  # legacy alias
            "conviction": round(self.conviction, 4),            # legacy alias
            "flow_trigger_allowed": self.flow_trigger_allowed,
            "reasons": list(self.reasons),
            "unavailable_reasons": list(self.unavailable_reasons),
        }


def _validate_score(name: str, value: float) -> None:
    if not (0.0 <= value <= 100.0):
        raise ValueError(f"{name} must be 0.0-100.0, got {value}")


def _validate_unit(name: str, value: float) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{name} must be 0.0-1.0, got {value}")


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 4)
