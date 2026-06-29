"""
ScoreForeignFlowUseCase.

Application-layer deterministic scoring of foreign broker-flow evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from src.domain.value_objects.foreign_flow_score_breakdown import ForeignFlowScoreBreakdown


@dataclass(frozen=True)
class EvidenceComponentPolicy:
    enabled: bool = True
    weight: float = 0.0


@dataclass(frozen=True)
class RsiEvidencePolicy(EvidenceComponentPolicy):
    low: float = 25.0
    peak: float = 40.0
    high: float = 75.0
    missing_fraction: float = 0.5


@dataclass(frozen=True)
class StreakEvidencePolicy(EvidenceComponentPolicy):
    tau_days: float = 7.0


@dataclass(frozen=True)
class LinearSaturationPolicy(EvidenceComponentPolicy):
    saturate_at: float = 10.0


@dataclass(frozen=True)
class BollingerSqueezePolicy(EvidenceComponentPolicy):
    tight_pctile: float = 0.20
    loose_pctile: float = 0.40


@dataclass(frozen=True)
class BciEvidencePolicy:
    enabled: bool = True
    cluster_points: float = 15.0
    stable_points: float = 5.0


@dataclass(frozen=True)
class ForeignFlowScorePolicy:
    max_score: float = 120.0
    consistency: EvidenceComponentPolicy = field(
        default_factory=lambda: EvidenceComponentPolicy(weight=40.0)
    )
    streak: StreakEvidencePolicy = field(
        default_factory=lambda: StreakEvidencePolicy(weight=30.0)
    )
    vwap_discount: LinearSaturationPolicy = field(
        default_factory=lambda: LinearSaturationPolicy(weight=20.0, saturate_at=10.0)
    )
    rsi_headroom: RsiEvidencePolicy = field(
        default_factory=lambda: RsiEvidencePolicy(weight=10.0)
    )
    foreign_flow_ratio: LinearSaturationPolicy = field(
        default_factory=lambda: LinearSaturationPolicy(weight=10.0, saturate_at=20.0)
    )
    bb_squeeze: BollingerSqueezePolicy = field(
        default_factory=lambda: BollingerSqueezePolicy(weight=10.0)
    )
    bci: BciEvidencePolicy = field(default_factory=BciEvidencePolicy)


@dataclass(frozen=True)
class ScoreForeignFlowRequest:
    ticker: str
    snapshot_date: date
    net_buy_ratio: float
    consecutive_streak: int
    vwap_discount_pct: float | None
    rsi: float | None
    avg_flow_ratio: float | None
    bb_width_pctile: float | None
    bci_label: str | None
    bci_tier1_count: int = 0


@dataclass(frozen=True)
class ScoreForeignFlowResponse:
    evidence: ForeignFlowScoreBreakdown


class ScoreForeignFlowUseCase:
    """Score foreign broker-flow evidence from already-computed ticker facts."""

    def __init__(self, policy: ForeignFlowScorePolicy | None = None) -> None:
        self._policy = policy or ForeignFlowScorePolicy()

    def execute(
        self,
        request: ScoreForeignFlowRequest,
    ) -> ScoreForeignFlowResponse:
        p = self._policy
        breakdown: dict[str, float] = {}

        breakdown["cons"] = (
            max(0.0, min(request.net_buy_ratio, 1.0)) * p.consistency.weight
            if p.consistency.enabled else 0.0
        )

        if p.streak.enabled:
            tau = max(p.streak.tau_days, 0.01)
            streak = max(request.consecutive_streak, 0)
            breakdown["streak"] = p.streak.weight * (1.0 - math.exp(-streak / tau))
        else:
            breakdown["streak"] = 0.0

        if p.vwap_discount.enabled:
            d = max(0.0, min(request.vwap_discount_pct or 0.0, p.vwap_discount.saturate_at))
            breakdown["vwap"] = d / p.vwap_discount.saturate_at * p.vwap_discount.weight
        else:
            breakdown["vwap"] = 0.0

        breakdown["rsi"] = self._score_rsi(request.rsi, p.rsi_headroom)

        if p.foreign_flow_ratio.enabled:
            fr = max(0.0, min(request.avg_flow_ratio or 0.0, p.foreign_flow_ratio.saturate_at))
            breakdown["flow"] = fr / p.foreign_flow_ratio.saturate_at * p.foreign_flow_ratio.weight
        else:
            breakdown["flow"] = 0.0

        breakdown["bb"] = self._score_bb(request.bb_width_pctile, p.bb_squeeze)
        breakdown["inst"] = self._score_bci(request.bci_label, p.bci)

        rounded_breakdown = {
            key: round(value, 1)
            for key, value in breakdown.items()
        }
        total = round(min(sum(breakdown.values()), p.max_score), 1)

        return ScoreForeignFlowResponse(
            evidence=ForeignFlowScoreBreakdown(
                ticker=request.ticker,
                snapshot_date=request.snapshot_date,
                accum_score=total,
                max_score=p.max_score,
                breakdown=tuple(rounded_breakdown.items()),
                net_buy_ratio=request.net_buy_ratio,
                consecutive_streak=request.consecutive_streak,
                vwap_discount_pct=request.vwap_discount_pct,
                rsi=request.rsi,
                avg_flow_ratio=request.avg_flow_ratio,
                bb_width_pctile=request.bb_width_pctile,
                bci_label=request.bci_label,
                bci_tier1_count=request.bci_tier1_count,
            )
        )

    @staticmethod
    def _score_rsi(rsi: float | None, policy: RsiEvidencePolicy) -> float:
        if not policy.enabled:
            return 0.0
        if rsi is None:
            return policy.weight * policy.missing_fraction
        if rsi <= policy.low or rsi >= policy.high:
            return 0.0
        if rsi <= policy.peak:
            return (rsi - policy.low) / (policy.peak - policy.low) * policy.weight
        return (policy.high - rsi) / (policy.high - policy.peak) * policy.weight

    @staticmethod
    def _score_bb(pctile: float | None, policy: BollingerSqueezePolicy) -> float:
        if not policy.enabled or pctile is None:
            return 0.0
        if pctile <= policy.tight_pctile:
            return policy.weight - pctile / policy.tight_pctile * (policy.weight / 2)
        if pctile <= policy.loose_pctile:
            return (policy.weight / 2) - (
                (pctile - policy.tight_pctile) / (policy.loose_pctile - policy.tight_pctile)
            ) * (policy.weight / 2)
        return 0.0

    @staticmethod
    def _score_bci(label: str | None, policy: BciEvidencePolicy) -> float:
        if not policy.enabled:
            return 0.0
        if label == "CLUSTER":
            return policy.cluster_points
        if label == "STABLE":
            return policy.stable_points
        return 0.0
