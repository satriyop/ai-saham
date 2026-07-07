"""Company quality context evidence — ticker-alpha conviction diagnostics (Phase I prep).

DIAGNOSTIC-ONLY: persisted at observation time for replay and attribution.
Feeds the Alpha/Trigger `company_quality_context` slot as coverage/diagnostic
evidence, but its DIAGNOSTIC registration gives it zero effective score authority
(effective_weight resolves to 0.0). Never affects DecisionPolicy, RiskEngine, or
TradeSetup sizing.

Represents contextual conviction / ticker-alpha ONLY: valuation, analyst revision,
insider/ownership quality, and CAPPED generic seasonality. It MUST NOT contain
liquidity gate, free-float gate, Piotroski, bandar distribution block, or technical
gate logic — those remain RiskEngine responsibilities (see docs/signal_refactor.md
lines 1842-1844).

Deferred axes (no data source/computation exists in the codebase):
  - earnings_trend        (kept as a None-valued axis so Phase I knows it exists)
  - configured event alpha (MSCI/FTSE, dividend-chase windows, market calendar)

All sub-scores are computed from local enrichment already present on SignalContext.
No external provider or new fetch is required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus


@dataclass(frozen=True)
class CompanyQualityContextEvidence:
    """
    Company quality / ticker-alpha context evidence for a single ticker.

    Fields
    ------
    valuation_score        Forward-P/E derived valuation attractiveness (0-100).
    earnings_trend_score   Deferred axis — always None (no producer yet).
    analyst_score          Analyst consensus conviction (0-100).
    insider_score          Insider net-buy direction (0-100).
    seasonality_score      Generic seasonality edge (0-100), CAPPED in aggregate.
    present_axes           Names of axes whose sub-score was available.
    aggregate_score        Coverage-weighted, seasonality-capped mean of present
                           axes (0-100). None when no axis is present.
    coverage_score         present_axis_count / scored_axis_count (0.0-1.0).
    evidence_status        Always DIAGNOSTIC in this phase.
    reasons                Human-readable reason strings.
    unavailable_reasons    Why specific axes could not be computed.
    metadata               Per-axis sub-scores and aggregation weights for
                           Phase I attribution.
    """

    valuation_score: float | None
    earnings_trend_score: float | None
    analyst_score: float | None
    insider_score: float | None
    seasonality_score: float | None
    present_axes: tuple[str, ...]
    aggregate_score: float | None
    coverage_score: float               # [0, 1]
    evidence_status: EvidenceStatus     # always DIAGNOSTIC in this phase
    reasons: tuple[str, ...]
    unavailable_reasons: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    _SCORE_FIELDS = (
        "valuation_score",
        "earnings_trend_score",
        "analyst_score",
        "insider_score",
        "seasonality_score",
    )

    def __post_init__(self) -> None:
        if not (0.0 <= self.coverage_score <= 1.0):
            raise ValueError(
                f"coverage_score must be in [0,1], got {self.coverage_score}"
            )
        for name in self._SCORE_FIELDS:
            value = getattr(self, name)
            if value is not None and not (0.0 <= value <= 100.0):
                raise ValueError(f"{name} must be in [0,100], got {value}")
        if self.aggregate_score is not None and not (
            0.0 <= self.aggregate_score <= 100.0
        ):
            raise ValueError(
                f"aggregate_score must be in [0,100], got {self.aggregate_score}"
            )

    def to_dict(self) -> dict[str, Any]:
        def _round(value: float | None) -> float | None:
            return round(value, 4) if value is not None else None

        return {
            "valuation_score": _round(self.valuation_score),
            "earnings_trend_score": _round(self.earnings_trend_score),
            "analyst_score": _round(self.analyst_score),
            "insider_score": _round(self.insider_score),
            "seasonality_score": _round(self.seasonality_score),
            "present_axes": list(self.present_axes),
            "aggregate_score": _round(self.aggregate_score),
            "coverage_score": round(self.coverage_score, 4),
            "evidence_status": self.evidence_status.value,
            "reasons": list(self.reasons),
            "unavailable_reasons": list(self.unavailable_reasons),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompanyQualityContextEvidence":
        return cls(
            valuation_score=data.get("valuation_score"),
            earnings_trend_score=data.get("earnings_trend_score"),
            analyst_score=data.get("analyst_score"),
            insider_score=data.get("insider_score"),
            seasonality_score=data.get("seasonality_score"),
            present_axes=tuple(data.get("present_axes") or []),
            aggregate_score=data.get("aggregate_score"),
            coverage_score=data.get("coverage_score", 0.0),
            evidence_status=EvidenceStatus(
                data.get("evidence_status", EvidenceStatus.DIAGNOSTIC.value)
            ),
            reasons=tuple(data.get("reasons") or []),
            unavailable_reasons=tuple(data.get("unavailable_reasons") or []),
            metadata=dict(data.get("metadata") or {}),
        )

    @classmethod
    def unavailable(cls, *, reason: str) -> "CompanyQualityContextEvidence":
        return cls(
            valuation_score=None,
            earnings_trend_score=None,
            analyst_score=None,
            insider_score=None,
            seasonality_score=None,
            present_axes=(),
            aggregate_score=None,
            coverage_score=0.0,
            evidence_status=EvidenceStatus.DIAGNOSTIC,
            reasons=(),
            unavailable_reasons=(reason,),
        )
