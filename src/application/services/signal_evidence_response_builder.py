"""
SignalEvidenceResponseBuilder — constructs the AssessSignalResponse and SignalAssessment.

Layer: Application
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.application.dto.assess_signal import AssessSignalResponse
from src.domain.value_objects.signal_assessment import SignalAssessment

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalEvidenceRequest
    from src.application.services.signal_evidence_group_scorer import SignalEvidenceGroupScores
    from src.application.services.signal_legacy_regime_conditioning import (
        LegacyRegimeConditioningResult,
    )
    from src.domain.value_objects.alpha_trigger_score import AlphaTriggerScore
    from src.domain.value_objects.decision_constraints import DecisionConstraints
    from src.domain.value_objects.setup_phase_readiness import SetupPhaseReadiness
    from src.domain.value_objects.signal_assessment import EntryQuality, SignalStrength


class SignalEvidenceResponseBuilder:
    @staticmethod
    def build(
        request: AssessSignalEvidenceRequest,
        group_scores: SignalEvidenceGroupScores,
        legacy_conditioning: LegacyRegimeConditioningResult,
        entry_quality: EntryQuality,
        decision_constraints: DecisionConstraints | None,
        alpha_trigger_score: AlphaTriggerScore | None,
        setup_readiness: "SetupPhaseReadiness | None" = None,
    ) -> AssessSignalResponse:
        breakdown = SignalEvidenceResponseBuilder._build_breakdown(
            setup_score=group_scores.setup_score,
            setup_present=group_scores.setup_present,
            flow_score=group_scores.flow_score,
            flow_present=group_scores.flow_present,
            signal_authority_coverage=group_scores.signal_authority_coverage,
            active_flags=group_scores.active_flags,
            flag_adj=group_scores.flag_adjustment,
            regime_conditioned=bool(legacy_conditioning.notes),
            gate_tightened=group_scores.gate_tightened,
        )

        rationale = SignalEvidenceResponseBuilder._build_rationale(
            ticker=request.ticker,
            final_score=group_scores.final_score,
            strength=group_scores.strength,
            entry_quality=entry_quality,
            setup_present=group_scores.setup_present,
            flow_present=group_scores.flow_present,
            signal_authority_coverage=group_scores.signal_authority_coverage,
            active_flags=group_scores.active_flags,
            flag_adj=group_scores.flag_adjustment,
            regime_notes=legacy_conditioning.notes,
            gate_tightened=group_scores.gate_tightened,
        )

        assessment = SignalAssessment(
            ticker=request.ticker,
            score=group_scores.final_score,
            strength=group_scores.strength,
            entry_quality=entry_quality,
            breakdown=breakdown,
            rationale=rationale,
            snapshot_date=request.snapshot_date,
            signal_authority_coverage=round(group_scores.signal_authority_coverage, 4),
            decision_constraints=decision_constraints,
            legacy_conditioned_score=legacy_conditioning.legacy_conditioned_score,
            raw_exact_score=round(group_scores.raw_exact_score, 4),
            alpha_trigger_score=alpha_trigger_score,
        )

        return AssessSignalResponse(
            ticker=request.ticker,
            assessment=assessment,
            coverage_warning=group_scores.coverage_warning,
            signal_authority_coverage=round(group_scores.signal_authority_coverage, 4),
            active_flags=group_scores.active_flags,
            flag_adjustment=group_scores.flag_adjustment,
            raw_group_score=group_scores.raw_group_score,
            signal_score_raw=group_scores.final_score,
            raw_exact_score=round(group_scores.raw_exact_score, 4),
            alpha_trigger_score=alpha_trigger_score,
            setup_readiness=setup_readiness,
        )

    @staticmethod
    def _build_breakdown(
        setup_score: float,
        setup_present: bool,
        flow_score: float,
        flow_present: bool,
        signal_authority_coverage: float,
        active_flags: tuple[str, ...],
        flag_adj: int,
        regime_conditioned: bool,
        gate_tightened: bool,
    ) -> tuple[tuple[str, float], ...]:
        entries: list[tuple[str, float]] = []
        if setup_present:
            entries.append(("setup_quality_group", round(setup_score, 2)))
        if flow_present:
            entries.append(("flow_confirmation_group", round(flow_score, 2)))
        entries.append(("signal_authority_coverage", round(signal_authority_coverage * 100.0, 2)))
        if flag_adj != 0:
            entries.append(("flag_adjustment", float(flag_adj)))
        if regime_conditioned:
            entries.append(("regime_conditioning", 1.0))
        if gate_tightened:
            entries.append(("gate_tightening", 1.0))
        return tuple(entries)

    @staticmethod
    def _build_rationale(
        ticker: str,
        final_score: int,
        strength: SignalStrength,
        entry_quality: EntryQuality,
        setup_present: bool,
        flow_present: bool,
        signal_authority_coverage: float,
        active_flags: tuple[str, ...],
        flag_adj: int,
        regime_notes: tuple[str, ...],
        gate_tightened: bool,
    ) -> tuple[str, ...]:
        lines: list[str] = []
        if not setup_present:
            lines.append("Setup quality: no evidence (excluded from score)")
        if not flow_present:
            lines.append("Flow confirmation: no evidence (excluded from score)")
        if active_flags:
            flag_str = ", ".join(active_flags)
            lines.append(f"Flags active: {flag_str} ({flag_adj:+d} pts)")
        for note in regime_notes:
            lines.append(note)
        if gate_tightened:
            lines.append("Gate tightening: ENTER → WATCH (regime gate_tightening=True)")
        lines.append(
            f"Signal authority coverage: {signal_authority_coverage:.0%} — "
            f"score {final_score} ({strength.value}/{entry_quality.value})"
        )
        return tuple(lines)
