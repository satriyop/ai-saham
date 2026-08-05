"""Risk gate audit artifacts for Package C2 persistence (research / child JSON).

These records do **not** change RiskAssessment verdict semantics. They capture
per-gate outcomes and GateContext completeness for fail-open vs fail-closed
proving. Persisted under observation_risk_assessments schema_version >= 2.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

from src.domain.rules.risk_gate import GateContext, GateOutcome, GateResult

if TYPE_CHECKING:
    from src.domain.value_objects.risk_assessment import RiskAssessment

GateEvaluationOutcome = Literal[
    "triggered",
    "pass",
    "skipped",
    "blocked_on_missing",
    "not_evaluated",
]

#: Persisted labels that mean "the gate asserted nothing about this ticker".
#: `not_evaluated` is excluded: that gate never ran (an earlier gate
#: short-circuited), which is a different fact from "ran but had no input".
UNEVALUABLE_OUTCOMES: frozenset[str] = frozenset({"skipped", "blocked_on_missing"})

GateTier = Literal["structural", "execution"]


def classify_gate_outcome(result: GateResult) -> GateEvaluationOutcome:
    """Map a GateResult to a C2 outcome label.

    Reads the typed `GateResult.outcome`; it does not parse the human-readable
    reason. The persisted label vocabulary is unchanged: an unevaluable gate is
    `skipped` when the missing-data policy lets it through and
    `blocked_on_missing` when the policy makes it block.
    """
    if result.outcome is GateOutcome.UNEVALUABLE:
        return "blocked_on_missing" if result.triggered else "skipped"
    return "triggered" if result.triggered else "pass"


@dataclass(frozen=True)
class GateEvaluationRecord:
    """One configured gate's evaluation (or short-circuit omission)."""

    gate: str
    tier: GateTier
    order: int
    evaluated: bool
    outcome: GateEvaluationOutcome
    triggered: bool | None
    reason: str | None
    confidence: int | None

    @property
    def is_unevaluable(self) -> bool:
        """True when this gate ran but had no usable input."""
        return self.outcome in UNEVALUABLE_OUTCOMES

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "tier": self.tier,
            "order": self.order,
            "evaluated": self.evaluated,
            "outcome": self.outcome,
            "triggered": self.triggered,
            "reason": self.reason,
            "confidence": self.confidence,
        }

    @classmethod
    def from_result(
        cls,
        *,
        gate_name: str,
        tier: GateTier,
        order: int,
        result: GateResult,
    ) -> GateEvaluationRecord:
        outcome = classify_gate_outcome(result)
        return cls(
            gate=gate_name,
            tier=tier,
            order=order,
            evaluated=True,
            outcome=outcome,
            triggered=result.triggered,
            reason=result.reason,
            confidence=result.confidence,
        )

    @classmethod
    def not_evaluated(
        cls,
        *,
        gate_name: str,
        tier: GateTier,
        order: int,
    ) -> GateEvaluationRecord:
        return cls(
            gate=gate_name,
            tier=tier,
            order=order,
            evaluated=False,
            outcome="not_evaluated",
            triggered=None,
            reason=None,
            confidence=None,
        )


@dataclass(frozen=True)
class GateContextCompleteness:
    """Point-in-time GateContext field presence for C2 missingness analysis."""

    ticker: str
    snapshot_date: date
    piotroski_f_score: int | None
    market_cap_idr: int | None
    free_float_pct: float | None
    five_day_accdist: str | None
    recent_candles_count: int
    latest_snapshot_present: bool

    @classmethod
    def from_context(cls, ctx: GateContext) -> GateContextCompleteness:
        return cls(
            ticker=ctx.ticker,
            snapshot_date=ctx.snapshot_date,
            piotroski_f_score=ctx.piotroski_f_score,
            market_cap_idr=ctx.market_cap_idr,
            free_float_pct=ctx.free_float_pct,
            five_day_accdist=ctx.five_day_accdist,
            recent_candles_count=len(ctx.recent_candles or ()),
            latest_snapshot_present=ctx.latest_snapshot is not None,
        )

    @property
    def missingness(self) -> dict[str, bool]:
        """True when the field is missing / empty for gate inputs."""
        return {
            "piotroski_f_score": self.piotroski_f_score is None,
            "market_cap_idr": self.market_cap_idr is None,
            "free_float_pct": self.free_float_pct is None,
            "five_day_accdist": self.five_day_accdist is None,
            "recent_candles": self.recent_candles_count == 0,
            "latest_snapshot": not self.latest_snapshot_present,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "snapshot_date": self.snapshot_date.isoformat(),
            "piotroski_f_score": self.piotroski_f_score,
            "market_cap_idr": self.market_cap_idr,
            "free_float_pct": self.free_float_pct,
            "five_day_accdist": self.five_day_accdist,
            "recent_candles_count": self.recent_candles_count,
            "latest_snapshot_present": self.latest_snapshot_present,
            "missingness": self.missingness,
        }


def build_risk_assessment_capture_dict(
    assessment: RiskAssessment,
    *,
    gate_evaluations: tuple[GateEvaluationRecord, ...] = (),
    gate_context: GateContextCompleteness | None = None,
) -> dict[str, Any]:
    """Merge verdict JSON with C2 audit blocks for child-table persistence."""
    payload = dict(assessment.to_dict())
    payload["gate_evaluations"] = [row.to_dict() for row in gate_evaluations]
    payload["gate_context"] = gate_context.to_dict() if gate_context is not None else None
    return payload
