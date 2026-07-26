"""Canonical SignalEngine use case for the pre-open directional baseline.

Layer: Application
"""

from __future__ import annotations

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.dto.pre_open_signal import (
    PreOpenSignalEvaluationInput,
    PreOpenSignalEvaluationResult,
)
from src.application.services.pre_open_directional_baseline import (
    evaluate_pre_open_directional_baseline,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.domain.value_objects.decision_constraints import DecisionConstraints
from src.domain.value_objects.pre_open_directional_baseline import (
    PreOpenAuctionQuality,
)
from src.domain.value_objects.pre_open_signal_evidence import PRE_OPEN_SETUP_FAMILY
from src.domain.value_objects.signal_assessment import (
    EntryQuality,
    PRE_OPEN_AUCTION_DIRECTION_IDENTITY,
    SignalAssessment,
    SignalStrength,
)


class AssessPreOpenDirectionalBaselineUseCase:
    """Render typed NCP evidence into the standard SignalEngine response."""

    def __init__(self, config: SignalEngineConfig) -> None:
        self._config = config

    def execute(
        self,
        evaluation_input: PreOpenSignalEvaluationInput,
        *,
        market_context=None,
    ) -> PreOpenSignalEvaluationResult | None:
        baseline = evaluate_pre_open_directional_baseline(
            evaluation_input.evidence,
            config=self._config.pre_open_directional_baseline,
        )
        if baseline is None:
            return None

        multiplier = market_context.signal_multiplier if market_context is not None else 1.0
        score = int(max(0, min(100, round(baseline.raw_score * multiplier))))
        strength, entry_quality = self._classify(score)
        constraint_reasons: list[str] = []

        if baseline.auction_quality is PreOpenAuctionQuality.CAUTION:
            entry_quality = _cap_entry_quality(entry_quality, EntryQuality.WATCH)
            constraint_reasons.append("auction_quality:CAUTION")
        elif baseline.auction_quality is PreOpenAuctionQuality.UNRELIABLE:
            entry_quality = EntryQuality.AVOID
            constraint_reasons.append("auction_quality:UNRELIABLE")

        if market_context is not None and market_context.gate_tightening:
            entry_quality = _cap_entry_quality(entry_quality, EntryQuality.WATCH)
            constraint_reasons.append(f"regime_gate_tightening:{market_context.regime.value}")

        if entry_quality is EntryQuality.AVOID:
            strength = SignalStrength.WEAK
        elif entry_quality is EntryQuality.WATCH and strength is SignalStrength.STRONG:
            strength = SignalStrength.MODERATE

        coverage = _authority_coverage(baseline)
        constraints = (
            DecisionConstraints(
                max_decision=entry_quality.value,
                regime=(market_context.regime.value if market_context is not None else None),
                regime_enter_allowed=not (
                    market_context is not None and market_context.gate_tightening
                ),
                regime_size_multiplier=multiplier,
                setup_family=PRE_OPEN_SETUP_FAMILY,
                setup_regime_action=None,
                effective_size_multiplier=multiplier,
                constraint_reasons=tuple(constraint_reasons),
            )
            if constraint_reasons
            else None
        )
        factors = baseline.factors
        breakdown = (
            ("directional_baseline", float(baseline.raw_score)),
            ("iep_gap_pct", factors.iep_gap_pct or 0.0),
            ("book_pressure", (factors.book_pressure or 0.0) * 100.0),
            ("delta_iev_ratio", (factors.delta_iev_ratio or 0.0) * 100.0),
            ("iev_intensity", factors.iev_intensity or 0.0),
        )
        rationale = baseline.rationale + tuple(
            f"quality:{reason}" for reason in baseline.quality_reasons
        )
        if factors.rsi_extension:
            rationale += ("context:rsi_extension",)
        if factors.unusual_volume:
            rationale += ("context:unusual_volume",)

        assessment = SignalAssessment(
            identity=PRE_OPEN_AUCTION_DIRECTION_IDENTITY,
            ticker=evaluation_input.ticker,
            score=score,
            strength=strength,
            entry_quality=entry_quality,
            breakdown=breakdown,
            rationale=rationale,
            snapshot_date=evaluation_input.snapshot_date,
            signal_authority_coverage=coverage,
            decision_constraints=constraints,
            raw_exact_score=float(baseline.raw_score),
        )
        response = AssessSignalResponse(
            ticker=evaluation_input.ticker,
            assessment=assessment,
            signal_score_raw=baseline.raw_score,
            signal_authority_coverage=coverage,
        )
        return PreOpenSignalEvaluationResult(
            response=response,
            baseline=baseline,
        )

    def _classify(self, score: int) -> tuple[SignalStrength, EntryQuality]:
        classification = self._config.classification
        if score >= classification.strong_min_score:
            return SignalStrength.STRONG, EntryQuality.ENTER
        if score >= classification.moderate_min_score:
            return SignalStrength.MODERATE, EntryQuality.WATCH
        return SignalStrength.WEAK, EntryQuality.AVOID


def _cap_entry_quality(
    quality: EntryQuality,
    maximum: EntryQuality,
) -> EntryQuality:
    ordered = (EntryQuality.AVOID, EntryQuality.WATCH, EntryQuality.ENTER)
    return ordered[min(ordered.index(quality), ordered.index(maximum))]


def _authority_coverage(baseline) -> float:
    factors = baseline.factors
    present = (
        factors.iep_gap_pct is not None,
        factors.book_pressure is not None,
        factors.delta_iev_ratio is not None,
        factors.iev_intensity is not None,
        factors.spread_pct is not None,
    )
    return sum(present) / len(present)
