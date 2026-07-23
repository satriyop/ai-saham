"""
AssessSignalEvidenceUseCase — staged evidence-first signal aggregator (Phase 4/5).

Phase 4: two-group staged aggregation replaces flat 6-factor weighted average.
  Group 1 — Setup Quality     (default weight 0.60)
  Group 2 — Flow Confirmation (default weight 0.40)

Phase 5: regime-conditional group score conditioning applied before renormalization.
  RISK_ON:   no conditioning (normal confidence).
  NEUTRAL:   weak flow confirmation discounted.
  RISK_OFF:  weak setup evidence (non-MATCH) discounted.
  VOLATILE:  both groups discounted.
  gate_tightening: ENTER → WATCH cap applied after classification.

Missing evidence excluded from weight denominator. Flags from SignalContext apply
score penalties as do-no-harm signals.

Layer: Application
Depends on: domain only + services + stdlib. No IO, no providers, no repositories.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from src.application.exceptions import NoProductionSignalEvidenceError
from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.services.decision_policy import DecisionPolicyService
from src.application.services.setup_phase_readiness_evaluator import (
    SetupPhaseReadinessEvaluator,
)
from src.application.services.signal_alpha_trigger_projection import SignalAlphaTriggerProjection
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.services.signal_evidence_group_scorer import (
    SignalEvidenceGroupScorer,
)
from src.application.services.signal_evidence_response_builder import SignalEvidenceResponseBuilder
from src.application.services.signal_legacy_regime_conditioning import (
    SignalLegacyRegimeConditioning,
)
from src.domain.value_objects.evidence_source_availability import AvailabilityEnforcementMode

if TYPE_CHECKING:
    from src.application.dto.assess_signal import AssessSignalResponse


class AssessSignalEvidenceUseCase:
    """
    Staged evidence-first signal aggregator.

    Two evidence groups contribute directional votes; flags from SignalContext
    apply score penalties for fundamental risk signals. Missing evidence lowers
    confidence but does not fabricate a neutral direction.
    """

    def __init__(self, config: SignalEngineConfig | None = None) -> None:
        self._config = config or SignalEngineConfig()

    def execute(self, request: AssessSignalEvidenceRequest) -> AssessSignalResponse:
        if request.setup_evidence is None and request.flow_confirmation_evidence is None:
            raise NoProductionSignalEvidenceError(
                "Canonical signal assessment requires setup or flow evidence."
            )

        # 1. Score evidence groups
        group_scores = SignalEvidenceGroupScorer.score(request, self._config)

        # 2. Compute legacy diagnostic conditioning
        legacy_conditioning = SignalLegacyRegimeConditioning.condition(
            setup_group_score=group_scores.setup_group_score,
            setup_present=group_scores.setup_present,
            flow_group_score=group_scores.flow_group_score,
            flow_present=group_scores.flow_present,
            market_context=request.market_context,
            config=self._config,
            flag_adjustment=group_scores.flag_adjustment,
        )

        # 3. Build typed setup-family readiness once (HIGH-2), then apply
        # flags/classification/decision policy. DecisionPolicyService is the
        # only gate that consumes signal_authority_coverage and readiness.
        setup_readiness = SetupPhaseReadinessEvaluator().evaluate(
            setup_family=request.setup_family,
            setup_evidence=request.setup_evidence,
            setup_phase=request.setup_phase,
        )
        decision_result = DecisionPolicyService(self._config.decision_policy).resolve(
            entry_quality=group_scores.entry_quality,
            score=group_scores.final_score,
            signal_authority_coverage=group_scores.signal_authority_coverage,
            market_context=request.market_context,
            setup_family=request.setup_family,
            setup_readiness=setup_readiness,
        )
        entry_quality = decision_result.entry_quality
        decision_constraints = decision_result.constraints

        # 4. Compute alpha/trigger score
        alpha_trigger_score = SignalAlphaTriggerProjection.build_score(
            request, self._config, group_scores
        )

        # 5. Build response — setup_readiness is the exact same object built
        # in step 3 and passed to DecisionPolicyService; never rebuilt here.
        response = SignalEvidenceResponseBuilder.build(
            request=request,
            group_scores=group_scores,
            legacy_conditioning=legacy_conditioning,
            entry_quality=entry_quality,
            decision_constraints=decision_constraints,
            alpha_trigger_score=alpha_trigger_score,
            setup_readiness=setup_readiness,
        )

        # 6. Attach availability diagnostics — sourced exclusively from the
        # canonical pre-score input (ADR-041 CANONICAL-EVIDENCE-BOUNDARY),
        # never from a second, independently-assembled availability check
        # after scoring. HIGH-2: signal_authority_coverage (step 1, via
        # SignalEvidenceGroupScorer) already consumed this same availability,
        # so enforcement mode is ENFORCED, not SHADOW — raw directional score
        # remains based on attached evidence only, unaffected by availability.
        if request.canonical_evidence is not None:
            setup_group = request.canonical_evidence.setup
            flow_group = request.canonical_evidence.flow
            if setup_group is not None or flow_group is not None:
                response = replace(
                    response,
                    setup_source_availability=(
                        setup_group.availability if setup_group is not None else None
                    ),
                    flow_source_availability=(
                        flow_group.availability if flow_group is not None else None
                    ),
                    availability_enforcement=AvailabilityEnforcementMode.ENFORCED,
                )
        return response
