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

from typing import TYPE_CHECKING

from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.services.decision_policy import DecisionPolicyService
from src.application.services.signal_alpha_trigger_projection import SignalAlphaTriggerProjection
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.services.signal_evidence_group_scorer import (
    SignalEvidenceGroupScorer,
)
from src.application.services.signal_evidence_response_builder import SignalEvidenceResponseBuilder
from src.application.services.signal_legacy_regime_conditioning import (
    SignalLegacyRegimeConditioning,
)

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
        # 1. Score evidence groups
        group_scores = SignalEvidenceGroupScorer.score(request, self._config)

        # 2. Compute legacy diagnostic conditioning
        legacy_conditioning = SignalLegacyRegimeConditioning.condition(
            setup_score=group_scores.setup_score,
            setup_present=group_scores.setup_present,
            flow_score=group_scores.flow_score,
            flow_present=group_scores.flow_present,
            market_context=request.market_context,
            config=self._config,
            flag_adjustment=group_scores.flag_adjustment,
        )

        # 3. Apply flags/classification/decision policy
        policy_coverage = (
            request.setup_phase.coverage_score
            if request.setup_phase is not None
            else group_scores.confidence
        )
        policy_conviction = (
            request.setup_phase.conviction_score
            if request.setup_phase is not None
            else group_scores.confidence
        )
        decision_result = DecisionPolicyService(self._config.decision_policy).resolve(
            entry_quality=group_scores.entry_quality,
            score=group_scores.final_score,
            coverage_score=policy_coverage,
            conviction_score=policy_conviction,
            market_context=request.market_context,
            setup_family=request.setup_family,
            setup_phase=request.setup_phase,
            setup_entry_authority=(
                request.setup_evidence.entry_authority
                if request.setup_evidence is not None
                else True
            ),
            setup_can_enter_from_phases=(
                request.setup_evidence.can_enter_from_phases
                if request.setup_evidence is not None
                else ()
            ),
        )
        entry_quality = decision_result.entry_quality
        decision_constraints = decision_result.constraints

        # 4. Compute alpha/trigger score
        alpha_trigger_score = SignalAlphaTriggerProjection.build_score(
            request, self._config, group_scores
        )

        # 5. Build response
        return SignalEvidenceResponseBuilder.build(
            request=request,
            group_scores=group_scores,
            legacy_conditioning=legacy_conditioning,
            entry_quality=entry_quality,
            decision_constraints=decision_constraints,
            alpha_trigger_score=alpha_trigger_score,
        )
