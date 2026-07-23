"""
ScoreAccumUseCase.

Application-layer deterministic scoring of foreign broker-flow evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from src.domain.value_objects.accum_score_breakdown import (
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
    AccumScoreBreakdown,
)


@dataclass(frozen=True)
class EvidenceComponentPolicy:
    enabled: bool = True
    weight: float = 0.0


@dataclass(frozen=True)
class RsiEvidencePolicy(EvidenceComponentPolicy):
    low: float = 25.0
    peak: float = 40.0
    high: float = 75.0


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
    cluster_points: float = 12.5
    stable_points: float = 4.2


@dataclass(frozen=True)
class AccumScorePolicy:
    max_score: float = 100.0
    consistency: EvidenceComponentPolicy = field(
        default_factory=lambda: EvidenceComponentPolicy(weight=33.3)
    )
    streak: StreakEvidencePolicy = field(
        default_factory=lambda: StreakEvidencePolicy(weight=25.0)
    )
    vwap_discount: LinearSaturationPolicy = field(
        default_factory=lambda: LinearSaturationPolicy(weight=16.7, saturate_at=10.0)
    )
    rsi_headroom: RsiEvidencePolicy = field(
        default_factory=lambda: RsiEvidencePolicy(weight=8.3)
    )
    foreign_flow_ratio: LinearSaturationPolicy = field(
        default_factory=lambda: LinearSaturationPolicy(weight=8.3, saturate_at=20.0)
    )
    bb_squeeze: BollingerSqueezePolicy = field(
        default_factory=lambda: BollingerSqueezePolicy(enabled=False, weight=8.3)
    )
    bci: BciEvidencePolicy = field(default_factory=BciEvidencePolicy)


@dataclass(frozen=True)
class ScoreAccumRequest:
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
class ScoreAccumResponse:
    evidence: AccumScoreBreakdown


class ScoreAccumUseCase:
    """Score foreign broker-flow evidence from already-computed ticker facts."""

    def __init__(self, policy: AccumScorePolicy | None = None) -> None:
        self._policy = policy or AccumScorePolicy()

    @property
    def policy(self) -> AccumScorePolicy:
        """Expose the active policy so other services (e.g.
        FlowConfirmationEvidenceBuilder) can derive weights from the same
        source of truth instead of maintaining a separate copy."""
        return self._policy

    def execute(
        self,
        request: ScoreAccumRequest,
    ) -> ScoreAccumResponse:
        p = self._policy
        components: list[ForeignFlowComponentScore] = [
            self._score_consistency(request.net_buy_ratio, p.consistency),
            self._score_streak(request.consecutive_streak, p.streak),
            self._score_linear_optional(
                key="vwap",
                value=request.vwap_discount_pct,
                policy=p.vwap_discount,
            ),
            self._score_rsi(request.rsi, p.rsi_headroom),
            self._score_linear_optional(
                key="flow",
                value=request.avg_flow_ratio,
                policy=p.foreign_flow_ratio,
            ),
            self._score_bb(request.bb_width_pctile, p.bb_squeeze),
            self._score_bci(request.bci_label, p.bci),
        ]

        rounded_components = tuple(
            ForeignFlowComponentScore(
                key=c.key,
                score_points=(
                    round(c.score_points, 1) if c.score_points is not None else None
                ),
                max_points=c.max_points,
                status=c.status,
            )
            for c in components
        )

        return ScoreAccumResponse(
            evidence=AccumScoreBreakdown(
                ticker=request.ticker,
                snapshot_date=request.snapshot_date,
                max_score=p.max_score,
                components=rounded_components,
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
    def _disabled(key: str, max_points: float) -> ForeignFlowComponentScore:
        return ForeignFlowComponentScore(
            key=key,
            score_points=None,
            max_points=max_points,
            status=ForeignFlowComponentStatus.DISABLED,
        )

    @staticmethod
    def _missing(key: str, max_points: float) -> ForeignFlowComponentScore:
        return ForeignFlowComponentScore(
            key=key,
            score_points=None,
            max_points=max(max_points, 0.01),
            status=ForeignFlowComponentStatus.MISSING,
        )

    @staticmethod
    def _available(key: str, score: float, max_points: float) -> ForeignFlowComponentScore:
        return ForeignFlowComponentScore(
            key=key,
            score_points=score,
            max_points=max_points,
            status=ForeignFlowComponentStatus.AVAILABLE,
        )

    def _score_consistency(
        self,
        net_buy_ratio: float,
        policy: EvidenceComponentPolicy,
    ) -> ForeignFlowComponentScore:
        if not policy.enabled:
            return self._disabled("cons", policy.weight)
        score = max(0.0, min(net_buy_ratio, 1.0)) * policy.weight
        return self._available("cons", score, policy.weight)

    def _score_streak(
        self,
        consecutive_streak: int,
        policy: StreakEvidencePolicy,
    ) -> ForeignFlowComponentScore:
        if not policy.enabled:
            return self._disabled("streak", policy.weight)
        tau = max(policy.tau_days, 0.01)
        streak = max(consecutive_streak, 0)
        score = policy.weight * (1.0 - math.exp(-streak / tau))
        return self._available("streak", score, policy.weight)

    def _score_linear_optional(
        self,
        *,
        key: str,
        value: float | None,
        policy: LinearSaturationPolicy,
    ) -> ForeignFlowComponentScore:
        if not policy.enabled:
            return self._disabled(key, policy.weight)
        if value is None:
            return self._missing(key, policy.weight)
        clamped = max(0.0, min(value, policy.saturate_at))
        score = clamped / policy.saturate_at * policy.weight
        return self._available(key, score, policy.weight)

    def _score_rsi(
        self,
        rsi: float | None,
        policy: RsiEvidencePolicy,
    ) -> ForeignFlowComponentScore:
        if not policy.enabled:
            return self._disabled("rsi", policy.weight)
        if rsi is None:
            return self._missing("rsi", policy.weight)
        if rsi <= policy.low or rsi >= policy.high:
            score = 0.0
        elif rsi <= policy.peak:
            score = (rsi - policy.low) / (policy.peak - policy.low) * policy.weight
        else:
            score = (policy.high - rsi) / (policy.high - policy.peak) * policy.weight
        return self._available("rsi", score, policy.weight)

    def _score_bb(
        self,
        pctile: float | None,
        policy: BollingerSqueezePolicy,
    ) -> ForeignFlowComponentScore:
        if not policy.enabled:
            return self._disabled("bb", policy.weight)
        if pctile is None:
            return self._missing("bb", policy.weight)
        if pctile <= policy.tight_pctile:
            score = policy.weight - pctile / policy.tight_pctile * (policy.weight / 2)
        elif pctile <= policy.loose_pctile:
            score = (policy.weight / 2) - (
                (pctile - policy.tight_pctile)
                / (policy.loose_pctile - policy.tight_pctile)
            ) * (policy.weight / 2)
        else:
            score = 0.0
        return self._available("bb", score, policy.weight)

    def _score_bci(
        self,
        label: str | None,
        policy: BciEvidencePolicy,
    ) -> ForeignFlowComponentScore:
        max_points = policy.cluster_points
        if not policy.enabled:
            return self._disabled("inst", max_points)
        if label is None:
            return self._missing("inst", max_points)
        if label == "CLUSTER":
            score = policy.cluster_points
        elif label == "STABLE":
            score = policy.stable_points
        elif label == "RETAIL-LED":
            score = 0.0
        else:
            raise ValueError(
                "bci_label must be CLUSTER, STABLE, RETAIL-LED, or None, "
                f"got {label!r}"
            )
        return self._available("inst", score, max_points)
