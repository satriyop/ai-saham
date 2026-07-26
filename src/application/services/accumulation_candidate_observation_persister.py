"""
AccumulationCandidateObservationPersister service.

Orchestrates candidate observation payload construction and persistence.

Layer: Application
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from src.application.services.accumulation_observation_fingerprint import (
    build_candidate_observation_payload,
    compute_accumulation_config_hash,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
    artifact_digest,
)
from src.domain.value_objects.risk_gate_audit import build_risk_assessment_capture_dict
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)

if TYPE_CHECKING:
    from src.application.dto import accumulation_screen as accumulation_dto
    from src.application.services.accumulation_candidate_evidence_builder import (
        AccumulationCandidateEvidenceBuilder,
    )
    from src.application.services.effective_market_session_resolver import (
        EffectiveMarketSession,
    )
    from src.application.services.primary_setup_family_resolver import (
        PrimarySetupFamilyResolver,
    )
    from src.application.use_case.evaluate_swing_setup_use_case import (
        SwingSetupCatalogConfig,
    )
    from src.domain.ports.learning_artifact_repositories import (
        LearningObservationRepository,
    )
    from src.domain.value_objects.signal_artifact_identity import (
        SemanticCompatibilityId,
    )


class AccumulationCandidateObservationPersister:
    def __init__(
        self,
        candidate_observations_repository: LearningObservationRepository | None,
        candidate_evidence_builder: AccumulationCandidateEvidenceBuilder,
        setup_family_resolver: PrimarySetupFamilyResolver,
        swing_setup_catalog: SwingSetupCatalogConfig | None,
    ) -> None:
        self._candidate_observations_repo = candidate_observations_repository
        self._candidate_evidence_builder = candidate_evidence_builder
        self._setup_family_resolver = setup_family_resolver
        self._swing_setup_catalog = swing_setup_catalog

    def persist(
        self,
        observation_candidates: list[accumulation_dto.AccumulationScreenObservationCandidate],
        snapshot_date: date,
        request: accumulation_dto.AccumulationScreenRequest,
        workflow: str = "screen_accum",
        effective_session: "EffectiveMarketSession | None" = None,
        *,
        observation_contract: str | None,
        semantic_compatibility_id: "SemanticCompatibilityId | None",
    ) -> int:
        """Persist observations for every evaluated candidate (pass + rejected).

        Returns the number of observations recorded. Returns 0 ONLY for the
        genuine "nothing to do" case — no repository or no evaluated candidates.
        This is the only place candidate observations are written — call it
        intentionally, not from read-only/diagnostic screen execution.

        Fails closed on failure (DQ-003 criterion 8): any error while building
        the payload or calling save_many (a locked DB, IntegrityError, schema
        mismatch, malformed canonical object, or any programmer error)
        propagates instead of being swallowed into a silent 0-count. A lost
        write must abort the run visibly, never masquerade as "0 saved".

        effective_session, when provided, is copied verbatim onto every
        persisted CandidateObservation as provenance metadata (DQ-002E). This
        method never resolves a session itself — callers that need one must
        resolve it upstream and pass it in.

        observation_contract and semantic_compatibility_id carry the lean
        DQ-003 identity. observation_contract MUST equal "accumulation-discovery.v1"
        — any other value is a contract violation and raises immediately
        (reserving a distinct contract for the future named-swing-setup
        producer, and preventing that population from overwriting or
        masquerading as discovery rows). A canonical write (repository present
        and candidates to write) with a None semantic_compatibility_id fails
        closed: a canonical row without a compatibility cohort tag is exactly
        what this slice prevents. Both are stamped verbatim onto every
        persisted CandidateObservation.
        """
        # Contract rejection is a hard invariant, not an expected data absence:
        # it must raise and propagate. So must every failure on the write path
        # below — there is no blanket try/except converting failures to a
        # 0-count (DQ-003 criterion 8 fail-closed contract).
        if observation_contract != ACCUMULATION_DISCOVERY_CONTRACT:
            raise ValueError(
                "observation_contract must be "
                f"{ACCUMULATION_DISCOVERY_CONTRACT!r}, got {observation_contract!r}"
            )
        if self._candidate_observations_repo is None or not observation_candidates:
            return 0
        if semantic_compatibility_id is None:
            raise ValueError(
                "canonical observation write requires a semantic_compatibility_id; "
                "a canonical row without a compatibility cohort tag is not allowed"
            )
        if effective_session is None:
            raise ValueError(
                "canonical accumulation capture requires one resolved effective session"
            )
        if (
            effective_session.latest_completed_session is None
            or effective_session.analysis_as_of is None
        ):
            raise ValueError(
                "canonical accumulation capture requires completed-session provenance"
            )
        captured_at = datetime.now(IDX_TIMEZONE)
        config_hash = compute_accumulation_config_hash(request)
        universe_id = artifact_digest({"tickers": sorted(request.tickers)})
        observations: list[LearningObservation] = []
        for oc in observation_candidates:
            c, screen_result, flow_ev = oc.candidate, oc.screen_result, oc.flow_evidence
            # HIGH-2: reuse the exact setup family and phase resolved once
            # in AccumulationCandidateSignalAssessor.assess() — the same
            # values SignalEngine scored against. Persistence must not
            # recompute or rewrite the assessed family/phase; strategy
            # evidence remains diagnostic-only input to the payload.
            setup_phase = c.setup_phase
            setup_family_result = c.setup_family_result
            strategy_evidence = (
                self._candidate_evidence_builder.build_candidate_strategy_evidence(
                    c,
                    setup_phase,
                    snapshot_date,
                    request,
                    setup_family=(
                        setup_family_result.primary_setup_family
                        if setup_family_result is not None
                        else None
                    ),
                )
            )
            builder = self._candidate_evidence_builder
            ia_evidence = builder.build_candidate_institutional_accumulation_evidence(
                c,
                snapshot_date,
            )
            tp_snapshot = self._candidate_evidence_builder.build_candidate_ticker_profile(
                c, snapshot_date
            )
            sc_evidence = self._candidate_evidence_builder.build_candidate_sector_context(
                c,
                snapshot_date,
                tp_snapshot,
            )
            cq_evidence = (
                self._candidate_evidence_builder.build_candidate_company_quality_context(
                    c,
                    snapshot_date,
                )
            )
            volatility_context = (
                self._candidate_evidence_builder.build_candidate_volatility_context(
                    c,
                    snapshot_date,
                )
            )
            data_as_of_date = c.latest_broker_date or c.latest_candle_date or snapshot_date
            decision_payload = build_candidate_observation_payload(
                c,
                screen_result=screen_result,
                flow_ev=flow_ev,
                setup_phase=setup_phase,
                strategy_evidence=strategy_evidence,
                ia_evidence=ia_evidence,
                tp_snapshot=tp_snapshot,
                sc_evidence=sc_evidence,
                cq_evidence=cq_evidence,
                setup_family_result=setup_family_result,
                volatility_context=volatility_context,
                snapshot_date=snapshot_date,
                captured_at=captured_at,
                request=request,
            )
            if c.risk_assessment is not None:
                decision_payload["risk"] = build_risk_assessment_capture_dict(
                    c.risk_assessment,
                    gate_evaluations=c.risk_gate_evaluations or (),
                    gate_context=c.risk_gate_context_completeness,
                )
            decision_payload["provenance"] = {
                "decision_at": effective_session.decision_at.isoformat(),
                "latest_completed_session": (
                    effective_session.latest_completed_session.isoformat()
                ),
                "analysis_as_of": effective_session.analysis_as_of.isoformat(),
                "market_session_name": effective_session.market_session_name,
                "is_eod_pending": effective_session.is_eod_pending,
                "resolution_source": effective_session.resolution_source,
                "resolution_notes": list(effective_session.notes),
                "data_as_of_date": data_as_of_date.isoformat(),
                "config_hash": config_hash,
                "workflow": workflow,
            }
            observations.append(
                LearningObservation.create(
                    purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                    policy_contract="accumulation_discovery.policy.v1",
                    horizon_contract="accum_20d",
                    compatibility_id=str(semantic_compatibility_id),
                    cutoff_at=effective_session.decision_at,
                    universe_id=universe_id,
                    window_id=(
                        f"{c.ticker}:{snapshot_date.isoformat()}:"
                        f"{request.window_days}:{data_as_of_date.isoformat()}"
                    ),
                    decision_payload=decision_payload,
                    captured_at=captured_at,
                )
            )
        return sum(
            self._candidate_observations_repo.add_observation(observation)
            for observation in observations
        )
