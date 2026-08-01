"""Application tests for GetAccumulationProducerReadinessUseCase (P0)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Sequence

import pytest

from src.application.services.accumulation_producer_readiness import ProducerReadinessStatus
from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2,
)
from src.application.use_case.get_accumulation_producer_readiness_use_case import (
    GetAccumulationProducerReadinessUseCase,
)
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS_V2,
    AccumPopulationBinding,
    AssessmentPurpose,
    LabelAvailability,
    LearningContractId,
    LearningObservation,
    LearningOutcomeLabel,
    OutcomeBasis,
    ProductionPolicySnapshot,
    recompute_path_label_fingerprint,
    stamp_universe_membership_id,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
COMPAT_A = "sha256:" + ("aa" * 32)
COMPAT_B = "sha256:" + ("bb" * 32)
OBS_CONTRACT = LearningContractId.ACCUMULATION_OBSERVATION.value
PRODUCER_CONTRACT = "accumulation-discovery.v2"
MATERIAL = "sha256:" + ("22" * 32)
MEMBERSHIP = ["BBCA", "BBRI"]
NAMED_ROSTER = ["ASII", "BBCA", "BBRI", "BMRI", "TLKM"]
UNIVERSE_ID = stamp_universe_membership_id(MEMBERSHIP)


def _payload(
    session_date: str,
    *,
    ticker: str = "BBCA",
    action: str = "WATCH",
    schema_version: int = CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    with_binding: bool = True,
    captured_at: datetime | None = None,
) -> dict:
    t = ticker.upper()
    cap = captured_at or datetime.fromisoformat(f"{session_date}T12:00:00+00:00")
    body = {
        "schema_version": schema_version,
        "artifact_type": "accumulation_session_observation",
        "ticker": t,
        "session_date": session_date,
        "captured_at": cap.isoformat(),
        "canonical_window": 7,
        "workflow": "research_accum_capture",
        "horizon_primary": "accum_10d",
        "shared": {
            "current_price": 100.0,
            "provenance": {
                "decision_at": f"{session_date}T12:00:00+00:00",
                "latest_completed_session": session_date,
                "analysis_as_of": session_date,
                "market_session_name": "regular",
                "is_eod_pending": False,
                "resolution_source": "test",
                "resolution_notes": [],
            },
        },
        "features_by_window": {
            "7": {
                "trade_setup": {"action": action},
                "signal": {},
                "candidate": {},
            },
            "30": {"trade_setup": {"action": action}, "signal": {}, "candidate": {}},
            "90": {"trade_setup": {"action": action}, "signal": {}, "candidate": {}},
        },
    }
    if with_binding and schema_version == CANDIDATE_OBSERVATION_SCHEMA_VERSION:
        body["population_binding"] = AccumPopulationBinding.create(
            membership_tickers=MEMBERSHIP,
            named_universe_tickers=NAMED_ROSTER,
            membership_session=session_date,
            pit_tradable_lookback_sessions=10,
            producer_source_revision="ai-saham@test+git:cafebabe",
        ).to_dict()
    return body


def _observation(
    *,
    day: int,
    compatibility_id: str,
    ticker: str = "BBCA",
    schema_version: int = CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    with_binding: bool = True,
) -> LearningObservation:
    at = datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc)
    t = ticker.upper()
    sd = f"2026-07-{day:02d}"
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=compatibility_id,
        cutoff_at=at,
        universe_id=UNIVERSE_ID,
        window_id=f"{t}:{sd}",
        decision_payload=_payload(
            sd,
            ticker=t,
            schema_version=schema_version,
            with_binding=with_binding,
            captured_at=at,
        ),
        captured_at=at,
    )


def _label(observation: LearningObservation) -> LearningOutcomeLabel:
    session = date.fromisoformat(str(observation.decision_payload["session_date"]))
    start = session + timedelta(days=1)
    end = start + timedelta(days=9)
    metrics = {
        "ticker": observation.decision_payload["ticker"],
        "signal_date": session.isoformat(),
        "label_window_start": start.isoformat(),
        "label_window_end": end.isoformat(),
        "entry_reference_price": 100.0,
        "close_return_pct": 3.5,
        "max_forward_return_pct": 5.0,
        "max_adverse_excursion_pct": -1.0,
        "days_to_peak": 2,
        "days_to_trough": 1,
    }
    return LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id=observation.observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="SUCCESS",
        metrics=metrics,
        fingerprint=recompute_path_label_fingerprint(
            observation_id=observation.observation_id,
            observation_artifact_digest=observation.artifact_digest,
            label_contract=LearningContractId.ACCUM_10D_LABEL,
        ),
        labeled_at=NOW,
    )


def _snapshot(policy_id: str, compatibility_id: str) -> ProductionPolicySnapshot:
    descriptor = ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2[policy_id]
    return ProductionPolicySnapshot.create(
        contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        learning_observation_contract_id=OBS_CONTRACT,
        producer_observation_contract=PRODUCER_CONTRACT,
        compatibility_id=compatibility_id,
        policy_id=policy_id,
        policy_version=descriptor.policy_version,
        decision_type=descriptor.decision_type,
        semantic_engine_contract_id=descriptor.semantic_engine_contract_id,
        material_config_hash=MATERIAL,
        canonical_payload={
            "policy_id": policy_id,
            "policy_version": descriptor.policy_version,
            "decision_type": descriptor.decision_type,
            "semantic_engine_contract_id": descriptor.semantic_engine_contract_id,
            "components": [],
        },
        source_revision="ai-saham@test+git:cafebabe",
        created_at=NOW,
    )


def _seed_full_v2(repo: SQLiteLearningArtifactRepository, compatibility_id: str) -> None:
    for pid in ACCUMULATION_PRODUCTION_POLICY_IDS_V2:
        assert repo.add_policy_snapshot(_snapshot(pid, compatibility_id))


class _WriteSpyRepo:
    """Wraps SQLite repo and fails if any write method is called."""

    def __init__(self, inner: SQLiteLearningArtifactRepository) -> None:
        self._inner = inner
        self.write_calls: list[str] = []

    def list_observations(self, purpose, *, compatibility_id=None):
        return self._inner.list_observations(purpose, compatibility_id=compatibility_id)

    def list_labels(self, observation_ids: Sequence[str]):
        return self._inner.list_labels(observation_ids)

    def list_policy_snapshots(self, *, purpose, compatibility_id):
        return self._inner.list_policy_snapshots(purpose=purpose, compatibility_id=compatibility_id)

    def add_observation(self, *args, **kwargs):
        self.write_calls.append("add_observation")
        raise AssertionError("status path must not write observations")

    def add_label(self, *args, **kwargs):
        self.write_calls.append("add_label")
        raise AssertionError("status path must not write labels")

    def add_policy_snapshot(self, *args, **kwargs):
        self.write_calls.append("add_policy_snapshot")
        raise AssertionError("status path must not write snapshots")

    def add_policy_snapshots_atomic(self, *args, **kwargs):
        self.write_calls.append("add_policy_snapshots_atomic")
        raise AssertionError("status path must not write snapshots")


def test_use_case_reports_legacy_and_ready_cohorts_without_writes(tmp_path) -> None:
    db = tmp_path / "learn.db"
    repo = SQLiteLearningArtifactRepository(db)

    # Schema-9 historical cohort (no population_binding) → LEGACY_RAW_ONLY.
    legacy_obs = [
        _observation(
            day=1,
            compatibility_id=COMPAT_A,
            ticker="BBCA",
            schema_version=LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
            with_binding=False,
        ),
        _observation(
            day=2,
            compatibility_id=COMPAT_A,
            ticker="BBRI",
            schema_version=LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
            with_binding=False,
        ),
    ]
    for o in legacy_obs:
        repo.add_observation(o)

    # Schema-10 + binding + labels + snapshots → CHALLENGE_INPUT_READY.
    ready_obs = [
        _observation(day=3, compatibility_id=COMPAT_B, ticker="BBCA"),
        _observation(day=4, compatibility_id=COMPAT_B, ticker="BBRI"),
    ]
    for o in ready_obs:
        repo.add_observation(o)
        repo.add_label(_label(o))
    _seed_full_v2(repo, COMPAT_B)

    spy = _WriteSpyRepo(repo)
    report = GetAccumulationProducerReadinessUseCase(
        observations=spy,
        labels=spy,
        policy_snapshots=spy,
    ).execute()

    assert spy.write_calls == []
    assert report.observation_count == 4
    assert report.cohort_count == 2
    by_id = {c.compatibility_id: c for c in report.cohorts}
    assert by_id[COMPAT_A].producer_status is ProducerReadinessStatus.LEGACY_RAW_ONLY
    assert by_id[COMPAT_B].producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY
    assert by_id[COMPAT_B].snapshot.verified_count == 7
    assert by_id[COMPAT_B].labels_by_horizon["H10"].available == 2

    payload = report.to_dict()
    assert payload["artifact_type"] == "accumulation_producer_readiness"
    assert payload["cohort_count"] == 2
    assert {c["producer_status"] for c in payload["cohorts"]} == {
        "LEGACY_RAW_ONLY",
        "CHALLENGE_INPUT_READY",
    }


def test_use_case_no_implicit_cohort_pooling(tmp_path) -> None:
    db = tmp_path / "learn.db"
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(
        day=1,
        compatibility_id=COMPAT_A,
        schema_version=LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
        with_binding=False,
    )
    o2 = _observation(day=1, compatibility_id=COMPAT_B, ticker="BBRI")
    repo.add_observation(o1)
    repo.add_observation(o2)
    _seed_full_v2(repo, COMPAT_B)
    repo.add_label(_label(o2))

    report = GetAccumulationProducerReadinessUseCase(
        observations=repo,
        labels=repo,
        policy_snapshots=repo,
    ).execute()
    by_id = {c.compatibility_id: c for c in report.cohorts}
    assert by_id[COMPAT_A].observation_count == 1
    assert by_id[COMPAT_A].snapshot.verified_count == 0
    assert by_id[COMPAT_B].observation_count == 1
    # One session only → COLLECTING even with full snapshots + H10.
    assert by_id[COMPAT_B].producer_status is ProducerReadinessStatus.COLLECTING


def test_use_case_rejects_non_accum_purpose(tmp_path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "x.db")
    uc = GetAccumulationProducerReadinessUseCase(
        observations=repo, labels=repo, policy_snapshots=repo
    )
    with pytest.raises(ValueError, match="ACCUMULATION_DISCOVERY"):
        uc.execute(AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION)
