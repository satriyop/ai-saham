"""Verify a stored signal observation via lean local recompute (DQ-005 Slice B).

Re-runs AccumulationScreenUseCase against local repos at the recorded cutoff,
compares a small field set, and reports MATCH / DRIFT / UNREPRODUCIBLE.
Does not persist. Does not refetch remote providers. Does not replace
retrieval-only (Slice A).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Protocol

from src.application.dto.accumulation_screen import (
    AccumulationScreenObservationCandidate,
    AccumulationScreenRequest,
)
from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.accumulation_observation_fingerprint import (
    build_candidate_observation_payload,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.retrieve_stored_signal_observation_use_case import (
    ObservationSelectionStatus,
    RetrieveStoredSignalObservationRequest,
    RetrieveStoredSignalObservationUseCase,
    StoredObservationIdentity,
)
from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
    CandidateObservationsRepository,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE, MARKET_CLOSE
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId
from src.domain.value_objects.signal_observation_fingerprint import (
    SignalObservationFingerprint,
)


class ObservationVerifyMode(str, Enum):
    VERIFY_LOCAL_RECOMPUTE = "VERIFY_LOCAL_RECOMPUTE"


class ObservationVerifyStatus(str, Enum):
    AMBIGUOUS = "AMBIGUOUS"
    UNREPRODUCIBLE = "UNREPRODUCIBLE"
    MATCH = "MATCH"
    DRIFT = "DRIFT"


@dataclass(frozen=True)
class ObservationFieldDifference:
    field: str
    stored: Any
    recomputed: Any


@dataclass(frozen=True)
class ObservationCompareSnapshot:
    score: Any
    signal_authority_coverage: Any
    setup_phase: Any
    fingerprint_digest: str | None


class ScreenRequestBuilder(Protocol):
    def build(
        self,
        *,
        tickers: list[str],
        window_days: int,
        as_of_date: date | None = None,
        market_context: Any = None,
    ) -> AccumulationScreenRequest: ...


class AccumulationScreenRunner(Protocol):
    def execute(
        self,
        request: AccumulationScreenRequest,
        *,
        execution_context: SignalEvidenceExecutionContext,
    ) -> Any: ...


class SessionResolver(Protocol):
    def resolve(self, *, run_at: datetime) -> EffectiveMarketSession: ...


class CandidateEvidenceBuilder(Protocol):
    def build_candidate_strategy_evidence(self, *args: Any, **kwargs: Any) -> Any: ...

    def build_candidate_institutional_accumulation_evidence(
        self, *args: Any, **kwargs: Any
    ) -> Any: ...

    def build_candidate_ticker_profile(self, *args: Any, **kwargs: Any) -> Any: ...

    def build_candidate_sector_context(self, *args: Any, **kwargs: Any) -> Any: ...

    def build_candidate_company_quality_context(
        self, *args: Any, **kwargs: Any
    ) -> Any: ...

    def build_candidate_volatility_context(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class VerifyStoredSignalObservationRequest:
    ticker: str
    snapshot_date: date
    observation_captured_at: datetime | None = None


@dataclass(frozen=True)
class VerifyStoredSignalObservationResponse:
    mode: ObservationVerifyMode = ObservationVerifyMode.VERIFY_LOCAL_RECOMPUTE
    status: ObservationVerifyStatus = ObservationVerifyStatus.UNREPRODUCIBLE
    selected_identity: StoredObservationIdentity | None = None
    candidates: tuple[StoredObservationIdentity, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)
    differences: tuple[ObservationFieldDifference, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)
    observation: CandidateObservation | None = None


_RESIDUAL_BACKFILL_NOTE = (
    "Residual risk: local candles/broker/enrichment filled after capture can "
    "change recompute results. MATCH is not promotion-grade bit-identity."
)


class VerifyStoredSignalObservationUseCase:
    """Select a stored observation, re-screen locally, compare a small field set."""

    def __init__(
        self,
        *,
        observations_repository: CandidateObservationsRepository,
        screen_use_case: AccumulationScreenRunner,
        screen_request_builder: ScreenRequestBuilder,
        session_resolver: SessionResolver,
        current_semantic_compatibility_id: SemanticCompatibilityId | str,
        candidate_evidence_builder: CandidateEvidenceBuilder,
    ) -> None:
        self._observations = observations_repository
        self._retrieve = RetrieveStoredSignalObservationUseCase(observations_repository)
        self._screen = screen_use_case
        self._request_builder = screen_request_builder
        self._session_resolver = session_resolver
        self._current_cohort_id = str(current_semantic_compatibility_id)
        self._evidence_builder = candidate_evidence_builder
        self.screen_execute_calls = 0

    def execute(
        self, request: VerifyStoredSignalObservationRequest
    ) -> VerifyStoredSignalObservationResponse:
        selection = self._retrieve.execute(
            RetrieveStoredSignalObservationRequest(
                ticker=request.ticker,
                snapshot_date=request.snapshot_date,
                observation_captured_at=request.observation_captured_at,
            )
        )

        if selection.status is ObservationSelectionStatus.NOT_FOUND:
            return VerifyStoredSignalObservationResponse(
                status=ObservationVerifyStatus.UNREPRODUCIBLE,
                reasons=("observation_not_found",),
                notes=(_RESIDUAL_BACKFILL_NOTE,),
            )

        if selection.status is ObservationSelectionStatus.AMBIGUOUS:
            return VerifyStoredSignalObservationResponse(
                status=ObservationVerifyStatus.AMBIGUOUS,
                candidates=selection.candidates,
                reasons=("multiple_observation_versions",),
                notes=(_RESIDUAL_BACKFILL_NOTE,),
            )

        observation = selection.observation
        identity = selection.selected_identity
        assert observation is not None
        assert identity is not None

        if not observation.config_hash:
            return VerifyStoredSignalObservationResponse(
                status=ObservationVerifyStatus.UNREPRODUCIBLE,
                selected_identity=identity,
                observation=observation,
                reasons=("non_canonical_observation",),
                notes=(_RESIDUAL_BACKFILL_NOTE,),
            )

        stored_cohort = (
            None
            if observation.semantic_compatibility_id is None
            else str(observation.semantic_compatibility_id)
        )
        if not stored_cohort or stored_cohort != self._current_cohort_id:
            return VerifyStoredSignalObservationResponse(
                status=ObservationVerifyStatus.UNREPRODUCIBLE,
                selected_identity=identity,
                observation=observation,
                reasons=(
                    (
                        "config_or_code_cohort_mismatch:"
                        f"stored={stored_cohort or '—'};"
                        f"current={self._current_cohort_id}"
                    ),
                ),
                notes=(_RESIDUAL_BACKFILL_NOTE,),
            )

        as_of = observation.analysis_as_of or observation.snapshot_date
        screen_request = self._request_builder.build(
            tickers=[observation.ticker.upper()],
            window_days=int(observation.window_sessions),
            as_of_date=as_of,
        )
        effective_session = self._session_resolver.resolve(
            run_at=datetime.combine(as_of, MARKET_CLOSE, tzinfo=IDX_TIMEZONE)
        )
        context = SignalEvidenceExecutionContext(
            effective_session=effective_session,
            source_availability_use_case=None,
        )

        self.screen_execute_calls += 1
        try:
            screen_response = self._screen.execute(
                screen_request, execution_context=context
            )
        except Exception as exc:  # noqa: BLE001 — map to UNREPRODUCIBLE reason
            return VerifyStoredSignalObservationResponse(
                status=ObservationVerifyStatus.UNREPRODUCIBLE,
                selected_identity=identity,
                observation=observation,
                reasons=(f"missing_local_source_data:{type(exc).__name__}",),
                notes=(_RESIDUAL_BACKFILL_NOTE,),
            )

        oc = _find_observation_candidate(
            screen_response.observation_candidates, observation.ticker
        )
        if oc is None or oc.candidate.signal_assessment is None:
            return VerifyStoredSignalObservationResponse(
                status=ObservationVerifyStatus.UNREPRODUCIBLE,
                selected_identity=identity,
                observation=observation,
                reasons=("missing_local_source_data",),
                notes=(_RESIDUAL_BACKFILL_NOTE,),
            )

        stored_snap = extract_stored_compare_snapshot(observation.payload or {})
        recomputed_snap = build_recomputed_compare_snapshot(
            oc,
            request=screen_request,
            snapshot_date=observation.snapshot_date,
            evidence_builder=self._evidence_builder,
        )
        differences = _diff_snapshots(stored_snap, recomputed_snap)
        status = (
            ObservationVerifyStatus.MATCH
            if not differences
            else ObservationVerifyStatus.DRIFT
        )
        return VerifyStoredSignalObservationResponse(
            status=status,
            selected_identity=identity,
            observation=observation,
            differences=differences,
            notes=(_RESIDUAL_BACKFILL_NOTE,),
        )


def fingerprint_digest_from_payload_dict(fingerprint_payload: dict[str, Any]) -> str:
    """Stable digest over the canonical label fingerprint surface."""
    fingerprint = SignalObservationFingerprint.from_dict(fingerprint_payload)
    canonical = fingerprint.to_canonical_dict()
    encoded = json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def extract_stored_compare_snapshot(payload: dict[str, Any]) -> ObservationCompareSnapshot:
    signal = payload.get("signal") or {}
    assessment = signal.get("assessment") or {}
    coverage = assessment.get("signal_authority_coverage")
    if coverage is None:
        coverage = signal.get("signal_authority_coverage")
    fingerprint_payload = payload.get("sub_signal_fingerprint") or {}
    setup_phase = fingerprint_payload.get("setup_phase_current")
    if setup_phase is None:
        setup_phase = fingerprint_payload.get("setup_readiness_current_phase")
    digest = (
        fingerprint_digest_from_payload_dict(fingerprint_payload)
        if fingerprint_payload
        else None
    )
    return ObservationCompareSnapshot(
        score=assessment.get("score"),
        signal_authority_coverage=coverage,
        setup_phase=setup_phase,
        fingerprint_digest=digest,
    )


def build_recomputed_compare_snapshot(
    oc: AccumulationScreenObservationCandidate,
    *,
    request: AccumulationScreenRequest,
    snapshot_date: date,
    evidence_builder: CandidateEvidenceBuilder,
) -> ObservationCompareSnapshot:
    candidate = oc.candidate
    signal = candidate.signal_assessment
    assert signal is not None

    setup_phase = candidate.setup_phase
    setup_family_result = candidate.setup_family_result
    strategy_evidence = evidence_builder.build_candidate_strategy_evidence(
        candidate,
        setup_phase,
        snapshot_date,
        request,
        setup_family=(
            setup_family_result.primary_setup_family
            if setup_family_result is not None
            else None
        ),
    )
    ia_evidence = evidence_builder.build_candidate_institutional_accumulation_evidence(
        candidate, snapshot_date
    )
    tp_snapshot = evidence_builder.build_candidate_ticker_profile(candidate, snapshot_date)
    sc_evidence = evidence_builder.build_candidate_sector_context(
        candidate, snapshot_date, tp_snapshot
    )
    cq_evidence = evidence_builder.build_candidate_company_quality_context(
        candidate, snapshot_date
    )
    volatility_context = evidence_builder.build_candidate_volatility_context(
        candidate, snapshot_date
    )
    payload = build_candidate_observation_payload(
        candidate,
        screen_result=oc.screen_result,
        flow_ev=oc.flow_evidence,
        setup_phase=setup_phase,
        strategy_evidence=strategy_evidence,
        ia_evidence=ia_evidence,
        tp_snapshot=tp_snapshot,
        sc_evidence=sc_evidence,
        cq_evidence=cq_evidence,
        setup_family_result=setup_family_result,
        volatility_context=volatility_context,
        snapshot_date=snapshot_date,
        captured_at=datetime.now(tz=IDX_TIMEZONE),
        request=request,
    )
    return extract_stored_compare_snapshot(payload)


def _find_observation_candidate(
    observation_candidates: list[AccumulationScreenObservationCandidate] | tuple,
    ticker: str,
) -> AccumulationScreenObservationCandidate | None:
    target = ticker.upper()
    for oc in observation_candidates:
        if oc.candidate.ticker.upper() == target:
            return oc
    return None


def _diff_snapshots(
    stored: ObservationCompareSnapshot,
    recomputed: ObservationCompareSnapshot,
) -> tuple[ObservationFieldDifference, ...]:
    diffs: list[ObservationFieldDifference] = []
    for name in (
        "score",
        "signal_authority_coverage",
        "setup_phase",
        "fingerprint_digest",
    ):
        left = getattr(stored, name)
        right = getattr(recomputed, name)
        if left != right:
            diffs.append(
                ObservationFieldDifference(field=name, stored=left, recomputed=right)
            )
    return tuple(diffs)
