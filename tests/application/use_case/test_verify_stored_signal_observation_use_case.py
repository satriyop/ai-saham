"""DQ-005 Slice B — lean local verify / recompute tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from types import SimpleNamespace

from src.application.dto.signal_evidence_execution_context import (
    SignalEvidenceExecutionContext,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.retrieve_stored_signal_observation_use_case import (
    StoredObservationIdentity,
)
from src.application.use_case.verify_stored_signal_observation_use_case import (
    ObservationVerifyMode,
    ObservationVerifyStatus,
    VerifyStoredSignalObservationRequest,
    VerifyStoredSignalObservationUseCase,
    extract_stored_compare_snapshot,
    fingerprint_digest_from_payload_dict,
)
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId


_COHORT = SemanticCompatibilityId(
    "sha256:" + ("a" * 64)
)
_OTHER_COHORT = SemanticCompatibilityId(
    "sha256:" + ("b" * 64)
)


class FakeObservationRepo:
    def __init__(self, observations=None):
        self.observations = list(observations or [])
        self.get_latest_calls = []

    def get_latest(self, ticker, snapshot_date):
        self.get_latest_calls.append((ticker, snapshot_date))
        raise AssertionError("verify must not use get_latest")

    def get_at(self, ticker, snapshot_date, captured_at):
        for obs in self.observations:
            if (
                obs.ticker.upper() == ticker.upper()
                and obs.snapshot_date == snapshot_date
                and obs.captured_at == captured_at
            ):
                return obs
        return None

    def list_all_by_date(self, snapshot_date):
        return [obs for obs in self.observations if obs.snapshot_date == snapshot_date]


@dataclass
class FakeScreen:
    response: object | None = None
    error: Exception | None = None
    calls: list = field(default_factory=list)

    def execute(self, request, *, execution_context):
        self.calls.append((request, execution_context))
        if self.error is not None:
            raise self.error
        return self.response


@dataclass
class FakeRequestBuilder:
    built: list = field(default_factory=list)

    def build(self, *, tickers, window_days, as_of_date=None, market_context=None):
        request = SimpleNamespace(
            tickers=tickers,
            window_days=window_days,
            as_of_date=as_of_date,
            market_context=market_context,
            strategy_name=None,
        )
        self.built.append(request)
        return request


@dataclass
class FakeSessionResolver:
    calls: list = field(default_factory=list)

    def resolve(self, *, run_at):
        self.calls.append(run_at)
        return EffectiveMarketSession(
            run_at=run_at,
            decision_at=run_at,
            latest_completed_session=run_at.date(),
            analysis_as_of=run_at.date(),
            market_session_name="REGULAR",
            is_eod_pending=False,
            resolution_source="test",
        )


class FakeEvidenceBuilder:
    """Unused when FakeScreen returns a full compare path via stub OC snapshot helper.

    For MATCH/DRIFT tests we stub build_recomputed by providing payload-aligned
    OC through a screen that returns a SimpleNamespace observation_candidates
    list and monkeypatch via a thin screen that already embeds compare fields
    through a custom use-case path — instead, tests that reach recompute use
    ``_StickyCompareScreen`` which bypasses evidence by returning candidates
    whose rebuild is intercepted via a dedicated FakeEvidenceBuilder that
    builds deterministic fingerprints through payload helper injection.

    Simpler approach for unit tests: subclass use case is avoided; we inject
    a screen returning observation_candidates and an evidence builder that
    makes ``build_candidate_observation_payload`` produce a known fingerprint
    by returning None for all evidence (fingerprint still builds from signal).
    """

    def build_candidate_strategy_evidence(self, *args, **kwargs):
        return None

    def build_candidate_institutional_accumulation_evidence(self, *args, **kwargs):
        return None

    def build_candidate_ticker_profile(self, *args, **kwargs):
        return None

    def build_candidate_sector_context(self, *args, **kwargs):
        return None

    def build_candidate_company_quality_context(self, *args, **kwargs):
        return None

    def build_candidate_volatility_context(self, *args, **kwargs):
        return None


def _fingerprint_payload(*, score_phase: str = "ACCUMULATION") -> dict:
    return {
        "setup_family": "foreign_bounce",
        "setup_phase_current": score_phase,
        "setup_readiness_current_phase": score_phase,
        "setup_readiness_status": "READY",
        "setup_readiness_missing_required_inputs": [],
        "setup_readiness_failed_requirements": [],
        "market_regime_at_signal": "RISK_ON",
        "signal_authority_coverage": 0.8,
        "rsi_at_signal": 55.0,
        "bb_width_pctile_at_signal": 0.2,
        "vwap_position_at_signal": -1.0,
        "volume_ratio_at_signal": 1.2,
        "cnfb_20d_at_signal": 1000.0,
        "foreign_participation_at_signal": 0.5,
        "foreign_concentration_at_signal": 0.4,
        "phase_detection_strength": 0.7,
        "phase_input_coverage": 1.0,
    }


def _payload(*, score: int = 72, coverage: float = 0.8, phase: str = "ACCUMULATION") -> dict:
    fp = _fingerprint_payload(score_phase=phase)
    fp["signal_authority_coverage"] = coverage
    return {
        "schema_version": 5,
        "signal": {
            "assessment": {
                "score": score,
                "signal_authority_coverage": coverage,
            },
            "signal_authority_coverage": coverage,
        },
        "sub_signal_fingerprint": fp,
    }


def _obs(
    *,
    captured_at: datetime,
    payload: dict | None = None,
    config_hash: str = "cfg-hash",
    cohort: SemanticCompatibilityId | None = _COHORT,
    analysis_as_of: date | None = None,
    window_sessions: int = 7,
    day: date = date(2026, 7, 3),
) -> CandidateObservation:
    return CandidateObservation(
        ticker="BBCA",
        snapshot_date=day,
        captured_at=captured_at,
        payload=payload if payload is not None else _payload(),
        window_sessions=window_sessions,
        config_hash=config_hash,
        data_as_of_date=day,
        analysis_as_of=analysis_as_of or day,
        semantic_compatibility_id=cohort,
        observation_contract="accumulation-discovery",
    )


def _use_case(*, observations, screen, cohort=_COHORT):
    return VerifyStoredSignalObservationUseCase(
        observations_repository=FakeObservationRepo(observations),
        screen_use_case=screen,
        screen_request_builder=FakeRequestBuilder(),
        session_resolver=FakeSessionResolver(),
        current_semantic_compatibility_id=cohort,
        candidate_evidence_builder=FakeEvidenceBuilder(),
    )


def test_ambiguous_does_not_call_screen():
    day = date(2026, 7, 3)
    observations = [
        _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0)),
        _obs(captured_at=datetime(2026, 7, 3, 10, 0, 0), window_sessions=30),
    ]
    screen = FakeScreen(response=SimpleNamespace(observation_candidates=[]))
    uc = _use_case(observations=observations, screen=screen)

    response = uc.execute(
        VerifyStoredSignalObservationRequest(ticker="BBCA", snapshot_date=day)
    )

    assert response.mode is ObservationVerifyMode.VERIFY_LOCAL_RECOMPUTE
    assert response.status is ObservationVerifyStatus.AMBIGUOUS
    assert response.reasons == ("multiple_observation_versions",)
    assert len(response.candidates) == 2
    assert screen.calls == []
    assert uc.screen_execute_calls == 0


def test_cohort_mismatch_is_unreproducible_without_screen():
    obs = _obs(
        captured_at=datetime(2026, 7, 3, 9, 0, 0),
        cohort=_OTHER_COHORT,
    )
    screen = FakeScreen(response=SimpleNamespace(observation_candidates=[]))
    uc = _use_case(observations=[obs], screen=screen, cohort=_COHORT)

    response = uc.execute(
        VerifyStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationVerifyStatus.UNREPRODUCIBLE
    assert response.reasons[0].startswith("config_or_code_cohort_mismatch:")
    assert screen.calls == []
    assert uc.screen_execute_calls == 0


def test_non_canonical_empty_config_hash_is_unreproducible_without_screen():
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0), config_hash="")
    screen = FakeScreen(response=SimpleNamespace(observation_candidates=[]))
    uc = _use_case(observations=[obs], screen=screen)

    response = uc.execute(
        VerifyStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationVerifyStatus.UNREPRODUCIBLE
    assert response.reasons == ("non_canonical_observation",)
    assert screen.calls == []


def test_missing_local_candidate_is_unreproducible():
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0))
    screen = FakeScreen(response=SimpleNamespace(observation_candidates=[]))
    uc = _use_case(observations=[obs], screen=screen)

    response = uc.execute(
        VerifyStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationVerifyStatus.UNREPRODUCIBLE
    assert response.reasons == ("missing_local_source_data",)
    assert uc.screen_execute_calls == 1


def test_screen_exception_maps_to_missing_local_source_data():
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0))
    screen = FakeScreen(error=RuntimeError("no candles"))
    uc = _use_case(observations=[obs], screen=screen)

    response = uc.execute(
        VerifyStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationVerifyStatus.UNREPRODUCIBLE
    assert response.reasons == ("missing_local_source_data:RuntimeError",)


def _assessment(*, score: int, coverage: float):
    return SimpleNamespace(
        assessment=SimpleNamespace(
            score=score,
            to_dict=lambda: {
                "score": score,
                "signal_authority_coverage": coverage,
                "strength": "MODERATE",
                "entry_quality": "OK",
                "breakdown": {},
            },
            signal_authority_coverage=coverage,
            strength=SimpleNamespace(value="MODERATE"),
            entry_quality=SimpleNamespace(value="OK"),
            breakdown_dict={},
            decision_constraints=None,
        ),
        signal_authority_coverage=coverage,
        coverage_warning=None,
        setup_readiness=None,
        active_flags=(),
        flag_adjustment=0,
        raw_group_score=None,
        raw_exact_score=None,
        alpha_trigger_score=None,
    )


def _candidate_for_recompute(*, score: int, coverage: float, phase: str):
    setup_phase = SimpleNamespace(
        current_phase=SimpleNamespace(value=phase),
        to_dict=lambda: {"current_phase": phase},
    )
    return SimpleNamespace(
        ticker="BBCA",
        signal_assessment=_assessment(score=score, coverage=coverage),
        setup_phase=setup_phase,
        setup_family_result=None,
        # Fields used by build_candidate_observation_payload / candidate.to_dict paths
        to_dict=lambda: {"ticker": "BBCA"},
        accum_score=1.0,
        trend="UP",
        consecutive_streak=2,
        latest_broker_date=date(2026, 7, 3),
        latest_candle_date=date(2026, 7, 3),
        rsi=55.0,
        bb_width_pctile=0.2,
        vwap_position=-1.0,
        volume_ratio=1.2,
        cnfb_20d=1000.0,
        foreign_participation=0.5,
        foreign_concentration=0.4,
    )


def test_match_when_recomputed_fields_equal(monkeypatch):
    payload = _payload(score=72, coverage=0.8, phase="ACCUMULATION")
    stored_snap = extract_stored_compare_snapshot(payload)
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0), payload=payload)

    oc = SimpleNamespace(
        candidate=_candidate_for_recompute(score=72, coverage=0.8, phase="ACCUMULATION"),
        screen_result="pass",
        flow_evidence=None,
    )
    screen = FakeScreen(response=SimpleNamespace(observation_candidates=[oc]))
    uc = _use_case(observations=[obs], screen=screen)

    # Force recomputed snapshot to equal stored (avoid full payload rebuild fragility).
    monkeypatch.setattr(
        "src.application.use_case.verify_stored_signal_observation_use_case.build_recomputed_compare_snapshot",
        lambda *args, **kwargs: stored_snap,
    )

    response = uc.execute(
        VerifyStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationVerifyStatus.MATCH
    assert response.differences == ()
    assert response.selected_identity is not None
    assert isinstance(response.selected_identity, StoredObservationIdentity)
    assert _RESIDUAL_NOTE in response.notes


def test_drift_lists_field_differences(monkeypatch):
    payload = _payload(score=72, coverage=0.8, phase="ACCUMULATION")
    stored_snap = extract_stored_compare_snapshot(payload)
    drifted = stored_snap.__class__(
        score=50,
        signal_authority_coverage=stored_snap.signal_authority_coverage,
        setup_phase=stored_snap.setup_phase,
        fingerprint_digest=stored_snap.fingerprint_digest,
    )
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0), payload=payload)
    oc = SimpleNamespace(
        candidate=_candidate_for_recompute(score=50, coverage=0.8, phase="ACCUMULATION"),
        screen_result="pass",
        flow_evidence=None,
    )
    screen = FakeScreen(response=SimpleNamespace(observation_candidates=[oc]))
    uc = _use_case(observations=[obs], screen=screen)
    monkeypatch.setattr(
        "src.application.use_case.verify_stored_signal_observation_use_case.build_recomputed_compare_snapshot",
        lambda *args, **kwargs: drifted,
    )

    response = uc.execute(
        VerifyStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationVerifyStatus.DRIFT
    assert len(response.differences) == 1
    assert response.differences[0].field == "score"
    assert response.differences[0].stored == 72
    assert response.differences[0].recomputed == 50


def test_fingerprint_digest_is_stable():
    fp = _fingerprint_payload()
    assert fingerprint_digest_from_payload_dict(fp) == fingerprint_digest_from_payload_dict(fp)


def test_adapter_does_not_own_compare_policy_symbols():
    """Architecture boundary: compare status enums live in application, not adapter."""
    import src.adapters.cli.research_signal_replay_commands as cli

    source = open(cli.__file__, encoding="utf-8").read()
    assert "ObservationFieldDifference" not in source
    assert "extract_stored_compare_snapshot" not in source
    assert "fingerprint_digest_from_payload_dict" not in source
    assert "--verify" in source


_RESIDUAL_NOTE = (
    "Residual risk: local candles/broker/enrichment filled after capture can "
    "change recompute results. MATCH is not promotion-grade bit-identity."
)
