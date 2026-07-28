"""Sector macro context evidence — routed per-sector macro drivers (ADR-053).

DIAGNOSTIC-ONLY in v1: persisted for display, fingerprint, and attribution.
Does not feed SignalEngine scoring, RiskEngine gates, or TradeSetup.

Distinct from peer-relative SectorContextEvidence (L2a): this VO answers
"which external macros matter for this sector?" not "how are peers trading?".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus

_MACRO_REGIMES = frozenset({"SUPPORTIVE", "NEUTRAL", "HEADWIND", "UNKNOWN"})
_FACTOR_LABELS = frozenset({"FAVORABLE", "NEUTRAL", "STRESSED", "UNAVAILABLE", "DISABLED"})


@dataclass(frozen=True)
class MacroFactorScore:
    """Single mapped macro factor evaluation for a sector."""

    name: str
    series: str
    value: float | None  # fractional session return; None if unavailable
    score: float | None  # 0.0–1.0; None if unavailable
    weight: float
    label: str  # FAVORABLE | NEUTRAL | STRESSED | UNAVAILABLE | DISABLED
    rationale: str

    def __post_init__(self) -> None:
        if self.label not in _FACTOR_LABELS:
            raise ValueError(f"invalid factor label: {self.label!r}")
        if self.score is not None and not (0.0 <= self.score <= 1.0):
            raise ValueError(f"score must be in [0,1], got {self.score}")
        if self.weight < 0.0:
            raise ValueError(f"weight must be >= 0, got {self.weight}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "series": self.series,
            "value": round(self.value, 6) if self.value is not None else None,
            "score": round(self.score, 4) if self.score is not None else None,
            "weight": self.weight,
            "label": self.label,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroFactorScore":
        return cls(
            name=str(data.get("name") or ""),
            series=str(data.get("series") or ""),
            value=data.get("value"),
            score=data.get("score"),
            weight=float(data.get("weight") or 0.0),
            label=str(data.get("label") or "UNAVAILABLE"),
            rationale=str(data.get("rationale") or ""),
        )


@dataclass(frozen=True)
class SectorMacroContextEvidence:
    """
    Routed macro-driver evidence for a single ticker via its universe group.

    Fields
    ------
    sector_group           universes.yaml group key (e.g. "energy"), or None.
    as_of_date             Snapshot date used for series windows.
    factors                Per-factor scores for the mapped library refs.
    composite_score        Weight-renormalized mean of available scores, or None.
    macro_regime           SUPPORTIVE | NEUTRAL | HEADWIND | UNKNOWN.
    coverage_score         available_factors / mapped_factors in [0, 1].
    evidence_status        Always DIAGNOSTIC in v1 (ADR-053).
    reasons                Human-readable computation notes.
    unavailable_reasons    Why factors or the whole snapshot failed.
    metadata               Optional diagnostic key/values (not for scoring).
    """

    sector_group: str | None
    as_of_date: date | None
    factors: tuple[MacroFactorScore, ...]
    composite_score: float | None
    macro_regime: str  # SUPPORTIVE | NEUTRAL | HEADWIND | UNKNOWN
    coverage_score: float
    evidence_status: EvidenceStatus
    reasons: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (0.0 <= self.coverage_score <= 1.0):
            raise ValueError(f"coverage_score must be in [0,1], got {self.coverage_score}")
        if self.macro_regime not in _MACRO_REGIMES:
            raise ValueError(f"invalid macro_regime: {self.macro_regime!r}")
        if self.composite_score is not None and not (0.0 <= self.composite_score <= 1.0):
            raise ValueError(f"composite_score must be in [0,1], got {self.composite_score}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector_group": self.sector_group,
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "factors": [f.to_dict() for f in self.factors],
            "composite_score": (
                round(self.composite_score, 4) if self.composite_score is not None else None
            ),
            "macro_regime": self.macro_regime,
            "coverage_score": round(self.coverage_score, 4),
            "evidence_status": self.evidence_status.value,
            "reasons": list(self.reasons),
            "unavailable_reasons": list(self.unavailable_reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SectorMacroContextEvidence":
        raw_date = data.get("as_of_date")
        as_of: date | None
        if raw_date is None or raw_date == "":
            as_of = None
        elif isinstance(raw_date, date):
            as_of = raw_date
        else:
            as_of = date.fromisoformat(str(raw_date))
        factors_raw = data.get("factors") or []
        factors = tuple(
            MacroFactorScore.from_dict(f) if isinstance(f, dict) else f for f in factors_raw
        )
        return cls(
            sector_group=data.get("sector_group"),
            as_of_date=as_of,
            factors=factors,
            composite_score=data.get("composite_score"),
            macro_regime=data.get("macro_regime", "UNKNOWN"),
            coverage_score=float(data.get("coverage_score") or 0.0),
            evidence_status=EvidenceStatus(
                data.get("evidence_status", EvidenceStatus.DIAGNOSTIC.value)
            ),
            reasons=tuple(data.get("reasons") or []),
            unavailable_reasons=tuple(data.get("unavailable_reasons") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    @classmethod
    def unavailable(
        cls,
        *,
        reason: str,
        sector_group: str | None = None,
        as_of_date: date | None = None,
    ) -> "SectorMacroContextEvidence":
        return cls(
            sector_group=sector_group,
            as_of_date=as_of_date,
            factors=(),
            composite_score=None,
            macro_regime="UNKNOWN",
            coverage_score=0.0,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=(),
            unavailable_reasons=(reason,),
        )
