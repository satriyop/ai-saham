"""
AccumulationCandidateObservationPersister service.

Orchestrates multi-window engine packs and ADR-056 session observation persistence.

Layer: Application
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from src.application.services.accumulation_observation_fingerprint import (
    build_candidate_observation_payload,
    build_session_observation_payload,
)
from src.domain.value_objects.diagnostic_producer_identity import (
    AccumulationDiagnosticBinding,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AccumPopulationBinding,
    AssessmentPurpose,
    LearningContractError,
    LearningContractId,
    LearningObservation,
    stable_learning_id,
    stamp_universe_membership_id,
    validate_accum_population_binding,
)
from src.domain.value_objects.risk_gate_audit import build_risk_assessment_capture_dict
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_HORIZON_CONTRACT,
    ACCUMULATION_DISCOVERY_POLICY_CONTRACT,
)
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

_REQUIRED_WINDOWS: tuple[int, ...] = (7, 30, 90)


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

    def persist_session_multi_window(
        self,
        *,
        window_results: dict[
            int,
            tuple[
                "accumulation_dto.AccumulationScreenRequest",
                list["accumulation_dto.AccumulationScreenObservationCandidate"],
            ],
        ],
        snapshot_date: date,
        effective_session: "EffectiveMarketSession",
        observation_contract: str | None,
        semantic_compatibility_id: "SemanticCompatibilityId | None",
        universe_tickers: list[str],
        population_binding: AccumPopulationBinding | dict[str, Any],
        diagnostic_bindings: dict[str, AccumulationDiagnosticBinding],
        canonical_window: int = 7,
    ) -> int:
        """Persist one ADR-056 session observation per ticker (windows 7/30/90 merged).

        ``window_results`` maps window_days → (request, observation_candidates).
        Tickers missing any required window are skipped (not half-written).
        Existing observation_ids are skipped (first write wins) so re-backfill
        does not conflict when ``captured_at`` changes the artifact digest.

        ``population_binding`` is the Option A typed authority for schema-10
        payloads (must agree with ``universe_tickers`` membership digest).
        """
        if observation_contract != ACCUMULATION_DISCOVERY_CONTRACT:
            raise ValueError(
                "observation_contract must be "
                f"{ACCUMULATION_DISCOVERY_CONTRACT!r}, got {observation_contract!r}"
            )
        if self._candidate_observations_repo is None:
            return 0
        if semantic_compatibility_id is None:
            raise ValueError(
                "canonical observation write requires a semantic_compatibility_id; "
                "a canonical row without a compatibility cohort tag is not allowed"
            )
        if (
            effective_session.latest_completed_session is None
            or effective_session.analysis_as_of is None
        ):
            raise ValueError("canonical accumulation capture requires completed-session provenance")
        for window in _REQUIRED_WINDOWS:
            if window not in window_results:
                raise ValueError(f"window_results missing required window {window}")

        if isinstance(population_binding, AccumPopulationBinding):
            binding_dict = population_binding.to_dict()
            binding_obj = population_binding
        elif isinstance(population_binding, dict):
            binding_obj = AccumPopulationBinding.from_mapping(population_binding)
            binding_dict = binding_obj.to_dict()
        else:
            raise ValueError(
                "population_binding must be AccumPopulationBinding or dict, "
                f"got {type(population_binding).__name__}"
            )

        # Locked population authority before any candidate processing or insert.
        # Unsupported names (e.g. idx30) must not poison schema-10 challenge corpus.
        universe_id = stamp_universe_membership_id(universe_tickers)
        if binding_obj.membership_digest != universe_id:
            raise ValueError(
                "population_binding.membership_digest must equal stamp of universe_tickers "
                f"(binding={binding_obj.membership_digest!r}, stamped={universe_id!r})"
            )
        if binding_obj.membership_session != snapshot_date.isoformat():
            raise ValueError(
                "population_binding.membership_session must equal snapshot_date "
                f"(binding={binding_obj.membership_session!r}, "
                f"snapshot={snapshot_date.isoformat()!r})"
            )
        try:
            validate_accum_population_binding(
                binding_obj,
                outer_universe_id=universe_id,
                economic_session=snapshot_date,
            )
        except LearningContractError as exc:
            raise ValueError(f"population_binding rejected before persist: {exc}") from exc

        # ticker -> window -> OC
        by_ticker: dict[str, dict[int, Any]] = {}
        for window, (_req, candidates) in window_results.items():
            for oc in candidates:
                ticker = oc.candidate.ticker.upper()
                by_ticker.setdefault(ticker, {})[int(window)] = oc

        captured_at = datetime.now(IDX_TIMEZONE)
        canon_req = window_results[canonical_window][0]
        market_context = getattr(canon_req, "market_context", None)
        shared_mce = (
            market_context.to_dict()
            if market_context is not None and hasattr(market_context, "to_dict")
            else None
        )

        saved = 0
        for ticker, packs in sorted(by_ticker.items()):
            if any(w not in packs for w in _REQUIRED_WINDOWS):
                continue
            window_id = f"{ticker}:{snapshot_date.isoformat()}"
            observation_id = stable_learning_id(
                LearningContractId.ACCUMULATION_OBSERVATION,
                {
                    "purpose": AssessmentPurpose.ACCUMULATION_DISCOVERY,
                    "policy_contract": ACCUMULATION_DISCOVERY_POLICY_CONTRACT,
                    "horizon_contract": ACCUMULATION_DISCOVERY_HORIZON_CONTRACT,
                    "compatibility_id": str(semantic_compatibility_id),
                    "cutoff_at": effective_session.decision_at,
                    "universe_id": universe_id,
                    "window_id": window_id,
                },
            )
            if self._candidate_observations_repo.get_observation(observation_id) is not None:
                # First write wins; re-runs must not conflict on captured_at digest.
                continue
            features_by_window: dict[str, dict[str, Any]] = {}
            screen_results: dict[str, str] = {}
            for window in _REQUIRED_WINDOWS:
                oc = packs[window]
                req = window_results[window][0]
                engine_pack = self._build_engine_pack(
                    oc,
                    snapshot_date=snapshot_date,
                    request=req,
                    captured_at=captured_at,
                    effective_session=effective_session,
                )
                features_by_window[str(window)] = engine_pack
                screen_results[str(window)] = str(oc.screen_result)

            canon_oc = packs[canonical_window]
            current_price = canon_oc.candidate.current_price
            if current_price is None or current_price <= 0:
                continue

            shared: dict[str, Any] = {
                "current_price": str(current_price),
                "universe_membership_note": "see capture response survivorship fields",
                "provenance": {
                    "decision_at": effective_session.decision_at.isoformat(),
                    "latest_completed_session": (
                        effective_session.latest_completed_session.isoformat()
                    ),
                    "analysis_as_of": effective_session.analysis_as_of.isoformat(),
                    "market_session_name": effective_session.market_session_name,
                    "is_eod_pending": effective_session.is_eod_pending,
                    "resolution_source": effective_session.resolution_source,
                    "resolution_notes": list(effective_session.notes),
                },
            }
            if shared_mce is not None:
                shared["market_context"] = shared_mce

            decision_payload = build_session_observation_payload(
                ticker=ticker,
                session_date=snapshot_date,
                captured_at=captured_at,
                canonical_window=canonical_window,
                features_by_window=features_by_window,
                shared=shared,
                screen_results_by_window=screen_results,
                population_binding=binding_dict,
                diagnostic_bindings=diagnostic_bindings,
            )
            observation = LearningObservation.create(
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                policy_contract=ACCUMULATION_DISCOVERY_POLICY_CONTRACT,
                horizon_contract=ACCUMULATION_DISCOVERY_HORIZON_CONTRACT,
                compatibility_id=str(semantic_compatibility_id),
                cutoff_at=effective_session.decision_at,
                universe_id=universe_id,
                window_id=window_id,
                decision_payload=decision_payload,
                captured_at=captured_at,
                # ADR-068 §6: provenance beside identity. Same value as the
                # population-binding stamp so one build produces both layers;
                # excluded from observation_id and artifact_digest.
                producer_source_revision=binding_obj.producer_source_revision,
            )
            if self._candidate_observations_repo.add_observation(observation):
                saved += 1
        return saved

    def _build_engine_pack(
        self,
        oc: "accumulation_dto.AccumulationScreenObservationCandidate",
        *,
        snapshot_date: date,
        request: "accumulation_dto.AccumulationScreenRequest",
        captured_at: datetime,
        effective_session: "EffectiveMarketSession",
    ) -> dict[str, Any]:
        """Full per-window engine pack (candidate + signal + risk + contexts)."""
        c, screen_result, flow_ev = oc.candidate, oc.screen_result, oc.flow_evidence
        setup_phase = c.setup_phase
        setup_family_result = c.setup_family_result
        strategy_evidence = self._candidate_evidence_builder.build_candidate_strategy_evidence(
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
        builder = self._candidate_evidence_builder
        ia_evidence = builder.build_candidate_institutional_accumulation_evidence(
            c,
            snapshot_date,
        )
        tp_snapshot = builder.build_candidate_ticker_profile(c, snapshot_date)
        sc_evidence = builder.build_candidate_sector_context(c, snapshot_date, tp_snapshot)
        smc_evidence = builder.build_candidate_sector_macro_context(c, snapshot_date)
        cq_evidence = builder.build_candidate_company_quality_context(c, snapshot_date)
        volatility_context = builder.build_candidate_volatility_context(c, snapshot_date)
        data_as_of_date = c.latest_broker_date or c.latest_candle_date or snapshot_date
        pack = build_candidate_observation_payload(
            c,
            screen_result=screen_result,
            flow_ev=flow_ev,
            setup_phase=setup_phase,
            strategy_evidence=strategy_evidence,
            ia_evidence=ia_evidence,
            tp_snapshot=tp_snapshot,
            sc_evidence=sc_evidence,
            smc_evidence=smc_evidence,
            cq_evidence=cq_evidence,
            setup_family_result=setup_family_result,
            volatility_context=volatility_context,
            snapshot_date=snapshot_date,
            captured_at=captured_at,
            request=request,
        )
        if c.risk_assessment is not None:
            pack["risk"] = build_risk_assessment_capture_dict(
                c.risk_assessment,
                gate_evaluations=c.risk_gate_evaluations or (),
                gate_context=c.risk_gate_context_completeness,
            )
        pack["window_days"] = int(request.window_days)
        pack["data_as_of_date"] = data_as_of_date.isoformat()
        pack["session_provenance"] = {
            "decision_at": effective_session.decision_at.isoformat(),
            "latest_completed_session": (
                effective_session.latest_completed_session.isoformat()
                if effective_session.latest_completed_session is not None
                else None
            ),
            "analysis_as_of": (
                effective_session.analysis_as_of.isoformat()
                if effective_session.analysis_as_of is not None
                else None
            ),
        }
        return pack
