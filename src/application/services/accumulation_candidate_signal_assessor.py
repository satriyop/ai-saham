"""Foreign-flow score assignment, signal assessment, flow evidence, setup
phase, and pass/reject classification.

Owns foreign-flow scoring, signal evaluation, flow evidence, setup phase
detection, and pass/reject classification. Does not persist observations,
sort candidates, or run sector-breadth or risk funnel post-processing.

Layer: Application
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from src.application.dto import accumulation_screen as accumulation_dto
from src.application.services.evidence_source_availability_assembler import (
    EvidenceSourceAvailabilityAssembler,
)
from src.application.services.signal_context_builder import (
    build_signal_context_from_candidate,
)
from src.application.use_case.score_foreign_flow_use_case import (
    ScoreForeignFlowRequest,
    ScoreForeignFlowUseCase,
)
from src.domain.value_objects.canonical_signal_evidence_input import (
    CanonicalSignalEvidenceInput,
    FlowEvidenceGroupInput,
)
from src.domain.value_objects.foreign_flow_evidence import ForeignFlowEvidence

if TYPE_CHECKING:
    from src.application.services.accumulation_candidate_evidence_builder import (
        AccumulationCandidateEvidenceBuilder,
    )
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )
    from src.application.services.flow_confirmation_evidence_builder import (
        FlowConfirmationEvidenceBuilder,
    )
    from src.application.services.signal_engine import SignalEngine
    from src.application.use_case.assess_source_availability_use_case import (
        AssessSourceAvailabilityUseCase,
    )
    from src.domain.value_objects.flow_confirmation_evidence import (
        FlowConfirmationEvidence,
    )

logger = logging.getLogger(__name__)


@dataclass
class CandidateSignalAssessmentResult:
    candidate: accumulation_dto.AccumulationCandidate
    flow_evidence: FlowConfirmationEvidence | None
    screen_result: str
    passes: bool


class AccumulationCandidateSignalAssessor:
    """Score foreign flow, assess signal, build flow evidence, detect setup
    phase, and classify.

    Classification order (preserved from original use case):
    1. Foreign-flow threshold rejection -> ``rejected_flow``
    2. Signal-score threshold rejection -> ``rejected_signal``
    3. Survivor -> ``pass``
    """

    def __init__(
        self,
        signal_engine: SignalEngine,
        flow_confirmation_builder: FlowConfirmationEvidenceBuilder,
        candidate_evidence_builder: AccumulationCandidateEvidenceBuilder,
        foreign_flow_score_uc: ScoreForeignFlowUseCase | None = None,
    ) -> None:
        self._signal_engine = signal_engine
        self._flow_confirmation_builder = flow_confirmation_builder
        self._candidate_evidence_builder = candidate_evidence_builder
        self._foreign_flow_score_uc = (
            foreign_flow_score_uc or ScoreForeignFlowUseCase()
        )

    def assess(
        self,
        candidate: accumulation_dto.AccumulationCandidate,
        *,
        request: accumulation_dto.AccumulationScreenRequest,
        as_of_date: date,
        consumed_broker_summaries: tuple,
        consumed_broker_daily_flows: tuple,
        effective_session: "EffectiveMarketSession",
        source_availability_use_case: "AssessSourceAvailabilityUseCase | None",
    ) -> CandidateSignalAssessmentResult:
        """Run signal assessment on the candidate and return the outcome."""
        # Phase 2.1: foreign-flow score assignment
        evidence_resp = self._foreign_flow_score_uc.execute(
            ScoreForeignFlowRequest(
                ticker=candidate.ticker,
                snapshot_date=as_of_date,
                net_buy_ratio=candidate.net_buy_ratio,
                consecutive_streak=candidate.consecutive_streak,
                vwap_discount_pct=candidate.vwap_discount_pct,
                rsi=candidate.rsi,
                avg_flow_ratio=candidate.avg_flow_ratio,
                bb_width_pctile=candidate.bb_width_pctile,
                bci_label=candidate.bci_label,
                bci_tier1_count=candidate.bci_tier1_count,
            )
        )
        candidate.foreign_flow_score_breakdown = evidence_resp.evidence
        candidate.foreign_flow_score = evidence_resp.evidence.foreign_flow_score
        candidate.foreign_flow_evidence = ForeignFlowEvidence.from_score_breakdown(
            evidence_resp.evidence,
            net_buy_days=candidate.net_buy_days,
            total_days=candidate.total_days,
            vwap_pct=candidate.vwap_pct,
            longer_term_context={
                "bci_label": candidate.bci_label,
                "bci_tier1_count": candidate.bci_tier1_count,
            },
        )

        signal_ctx = build_signal_context_from_candidate(
            ticker=candidate.ticker,
            snapshot_date=as_of_date,
            candidate=candidate,
            signal_engine=self._signal_engine,
        )

        # Flow evidence is built from candidate data already in memory — no
        # extra fetch. SetupEvidence is intentionally absent here: the batch
        # screener does not evaluate named setup patterns per ticker; that
        # happens only in the per-ticker swing workflow.
        flow_ev: FlowConfirmationEvidence | None = None
        built_flow = None
        try:
            built_flow = self._flow_confirmation_builder.build(
                candidate,
                analysis_date=as_of_date,
                consumed_broker_summaries=consumed_broker_summaries,
                consumed_broker_daily_flows=consumed_broker_daily_flows,
            )
        except (ValueError, TypeError):
            raise
        except Exception:
            built_flow = None

        if built_flow is not None:
            flow_ev = built_flow.evidence

        # HIGH-2: resolve the preliminary setup family exactly once, then
        # detect setup phase exactly once using that same family and flow
        # evidence — both BEFORE calling SignalEngine, and BEFORE building
        # canonical evidence. Store both on the candidate so persistence
        # reuses them verbatim instead of recomputing after scoring.
        setup_family_result = (
            self._candidate_evidence_builder.resolve_preliminary_setup_family_result(
                candidate
            )
        )
        setup_family = setup_family_result.primary_setup_family
        candidate.setup_family_result = setup_family_result
        candidate.setup_phase = (
            self._candidate_evidence_builder.detect_candidate_setup_phase(
                candidate, flow_ev, as_of_date, setup_family=setup_family
            )
        )

        canonical_evidence: CanonicalSignalEvidenceInput | None = None
        if built_flow is not None:
            # ADR-041 CANONICAL-EVIDENCE-BOUNDARY: availability is resolved
            # once, pre-score, from this exact provenance and bound
            # immediately into the canonical group — never a separate
            # post-score assembly, and never supplied to SignalEngine as a
            # loose evidence value disconnected from its provenance. The
            # screen never fabricates SetupEvidence — `setup=None` here means
            # a known family with absent setup evidence resolves to typed
            # UNAVAILABLE readiness, not a canonical ENTER.
            flow_availability = EvidenceSourceAvailabilityAssembler(
                source_availability_use_case
            ).assess_flow(
                effective_session=effective_session,
                provenance=built_flow.provenance,
            )
            canonical_evidence = CanonicalSignalEvidenceInput(
                setup=None,
                flow=FlowEvidenceGroupInput(
                    evidence=built_flow.evidence,
                    provenance=built_flow.provenance,
                    availability=flow_availability,
                ),
            )

        candidate.signal_assessment = self._signal_engine.evaluate_with_context(
            candidate.ticker,
            signal_ctx,
            canonical_evidence=canonical_evidence,
            setup_family=setup_family,
            setup_phase=candidate.setup_phase,
        )

        # Classification: first-match-wins (preserved order)
        if (
            request.min_foreign_flow_score_enabled
            and candidate.foreign_flow_score < request.min_foreign_flow_score
        ):
            return CandidateSignalAssessmentResult(
                candidate, flow_ev, "rejected_flow", False
            )

        if request.min_signal_score_enabled and (
            candidate.signal_assessment is None
            or candidate.signal_assessment.assessment.score < request.min_signal_score
        ):
            return CandidateSignalAssessmentResult(
                candidate, flow_ev, "rejected_signal", False
            )

        return CandidateSignalAssessmentResult(candidate, flow_ev, "pass", True)
