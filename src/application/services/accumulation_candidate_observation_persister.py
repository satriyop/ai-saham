"""
AccumulationCandidateObservationPersister service.

Orchestrates candidate observation payload construction and persistence.

Layer: Application
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from src.application.services.accumulation_observation_fingerprint import (
    build_candidate_observation_payload,
    compute_accumulation_config_hash,
)
from src.domain.ports.candidate_observations_repository import CandidateObservation
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
    from src.domain.ports.candidate_observations_repository import (
        CandidateObservationsRepository,
    )
    from src.domain.value_objects.signal_artifact_identity import (
        SemanticCompatibilityId,
    )

logger = logging.getLogger(__name__)


class AccumulationCandidateObservationPersister:
    def __init__(
        self,
        candidate_observations_repository: CandidateObservationsRepository | None,
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

        Returns the number of observations recorded (0 if there is no
        repository, nothing was evaluated, or persistence failed). This is the
        only place candidate observations are written — call it intentionally,
        not from read-only/diagnostic screen execution.

        effective_session, when provided, is copied verbatim onto every
        persisted CandidateObservation as provenance metadata (DQ-002E). This
        method never resolves a session itself — callers that need one must
        resolve it upstream and pass it in.

        observation_contract and semantic_compatibility_id carry the lean
        DQ-003 identity. observation_contract MUST equal "accumulation-discovery"
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
        # it must raise and propagate, so it lives BEFORE the broad
        # persistence try/except below (which converts provider/data failures
        # into a 0-count no-op).
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
        try:
            captured_at = datetime.now()
            config_hash = compute_accumulation_config_hash(request)
            observations = []
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
                observations.append(
                    CandidateObservation(
                        ticker=c.ticker,
                        snapshot_date=snapshot_date,
                        captured_at=captured_at,
                        workflow=workflow,
                        window_sessions=request.window_days,
                        data_as_of_date=data_as_of_date,
                        config_hash=config_hash,
                        decision_at=(
                            effective_session.decision_at if effective_session else None
                        ),
                        latest_completed_session=(
                            effective_session.latest_completed_session
                            if effective_session
                            else None
                        ),
                        analysis_as_of=(
                            effective_session.analysis_as_of if effective_session else None
                        ),
                        market_session_name=(
                            effective_session.market_session_name if effective_session else None
                        ),
                        is_eod_pending=(
                            effective_session.is_eod_pending if effective_session else None
                        ),
                        resolution_source=(
                            effective_session.resolution_source if effective_session else None
                        ),
                        resolution_notes=(
                            effective_session.notes if effective_session else ()
                        ),
                        observation_contract=observation_contract,
                        semantic_compatibility_id=semantic_compatibility_id,
                        payload=build_candidate_observation_payload(
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
                        ),
                    )
                )
            self._candidate_observations_repo.save_many(observations)
            return len(observations)
        except Exception as exc:
            logger.warning("Candidate observation persistence unavailable: %s", exc)
            return 0
