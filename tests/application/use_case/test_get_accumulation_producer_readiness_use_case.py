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
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
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
from src.domain.value_objects.trading_session_calendar_snapshot import (
    PATH_LABEL_METRICS_SCHEMA_VERSION,
    STOCKBIT_TRADING_SESSIONS_CONTRACT,
    TradingSessionCalendarSnapshot,
    label_window_digest,
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


def _weekday_sessions(start: date, end: date) -> tuple[date, ...]:
    out: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            out.append(current)
        current += timedelta(days=1)
    return tuple(out)


DEFAULT_SESSION_CALENDAR = KnownTradingSessionCalendar(
    sessions=_weekday_sessions(date(2026, 6, 1), date(2026, 9, 30)),
    coverage_start=date(2026, 6, 1),
    coverage_end=date(2026, 9, 30),
)
DEFAULT_CALENDAR_SNAPSHOT = TradingSessionCalendarSnapshot.create(
    coverage_start=date(2026, 6, 1),
    coverage_end=date(2026, 9, 30),
    ordered_sessions=DEFAULT_SESSION_CALENDAR.sessions,
    source_revision="stockbit.test.v1",
    captured_at=NOW,
)


def _snapshot_lookup(snapshot_id: str):
    if snapshot_id == DEFAULT_CALENDAR_SNAPSHOT.snapshot_id:
        return DEFAULT_CALENDAR_SNAPSHOT
    return None


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
        producer_source_revision="ai-saham@test",
    )


def _label(observation: LearningObservation) -> LearningOutcomeLabel:
    session = date.fromisoformat(str(observation.decision_payload["session_date"]))
    expected = DEFAULT_CALENDAR_SNAPSHOT.first_n_sessions_after(session, 10)
    assert expected is not None
    metrics = {
        "ticker": observation.decision_payload["ticker"],
        "signal_date": session.isoformat(),
        "label_window_start": expected[0].isoformat(),
        "label_window_end": expected[-1].isoformat(),
        "label_window_sessions": [s.isoformat() for s in expected],
        "calendar_snapshot_id": DEFAULT_CALENDAR_SNAPSHOT.snapshot_id,
        "calendar_contract_id": STOCKBIT_TRADING_SESSIONS_CONTRACT,
        "calendar_source_revision": DEFAULT_CALENDAR_SNAPSHOT.source_revision,
        "label_window_digest": label_window_digest(
            calendar_snapshot_id=DEFAULT_CALENDAR_SNAPSHOT.snapshot_id,
            label_contract_id=LearningContractId.ACCUM_10D_LABEL.value,
            signal_date=session,
            sessions=expected,
        ),
        "path_label_metrics_schema_version": PATH_LABEL_METRICS_SCHEMA_VERSION,
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

    # Current schema + binding + labels + snapshots → CHALLENGE_INPUT_READY.
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
        session_snapshot_lookup=_snapshot_lookup,
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
        session_snapshot_lookup=_snapshot_lookup,
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


def test_dual_snapshot_compat_drift_raises_integrity_not_legacy(tmp_path) -> None:
    """Dual compatibility_id rewrite fails closed on global integrity (never LEGACY)."""
    import json
    import sqlite3

    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        LearningArtifactReadIntegrityError,
    )

    db = tmp_path / "snap-drift.db"
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(day=1, compatibility_id=COMPAT_B, ticker="BBCA")
    o2 = _observation(day=2, compatibility_id=COMPAT_B, ticker="BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
        repo.add_label(_label(o))
    _seed_full_v2(repo, COMPAT_B)

    with sqlite3.connect(db) as conn:
        for sid, aj in conn.execute(
            "SELECT snapshot_id, artifact_json FROM learning_policy_snapshots"
        ):
            raw = json.loads(aj)
            raw["compatibility_id"] = "mutated-compat"
            conn.execute(
                "UPDATE learning_policy_snapshots SET compatibility_id=?, artifact_json=? "
                "WHERE snapshot_id=?",
                (
                    "mutated-compat",
                    json.dumps(raw, sort_keys=True, separators=(",", ":")),
                    sid,
                ),
            )
        conn.commit()

    with pytest.raises(LearningArtifactReadIntegrityError):
        GetAccumulationProducerReadinessUseCase(
            observations=repo,
            labels=repo,
            policy_snapshots=repo,
            session_snapshot_lookup=_snapshot_lookup,
        ).execute()


def test_dual_observation_purpose_drift_raises_integrity_not_empty(tmp_path) -> None:
    """Dual purpose rewrite fails closed on global integrity (never empty cohort)."""
    import json
    import sqlite3

    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        LearningArtifactReadIntegrityError,
    )

    db = tmp_path / "obs-drift.db"
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(day=1, compatibility_id=COMPAT_B, ticker="BBCA")
    o2 = _observation(day=2, compatibility_id=COMPAT_B, ticker="BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
        repo.add_label(_label(o))
    _seed_full_v2(repo, COMPAT_B)

    with sqlite3.connect(db) as conn:
        for oid, aj in conn.execute(
            "SELECT observation_id, artifact_json FROM learning_observations"
        ):
            raw = json.loads(aj)
            raw["purpose"] = AssessmentPurpose.SWING_TRADE_SETUP.value
            conn.execute(
                "UPDATE learning_observations SET purpose=?, artifact_json=? "
                "WHERE observation_id=?",
                (
                    AssessmentPurpose.SWING_TRADE_SETUP.value,
                    json.dumps(raw, sort_keys=True, separators=(",", ":")),
                    oid,
                ),
            )
        conn.commit()

    with pytest.raises(LearningArtifactReadIntegrityError):
        GetAccumulationProducerReadinessUseCase(
            observations=repo,
            labels=repo,
            policy_snapshots=repo,
            session_snapshot_lookup=_snapshot_lookup,
        ).execute()


def test_combined_label_anchor_mutation_raises_integrity(tmp_path) -> None:
    """Dual observation_id + dual label_id rewrite fails readiness closed."""
    import json
    import sqlite3

    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        LearningArtifactReadIntegrityError,
    )

    db = tmp_path / "label-drift.db"
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(day=1, compatibility_id=COMPAT_B, ticker="BBCA")
    o2 = _observation(day=2, compatibility_id=COMPAT_B, ticker="BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
        repo.add_label(_label(o))
    _seed_full_v2(repo, COMPAT_B)

    with sqlite3.connect(db) as conn:
        for i, (lid, aj) in enumerate(
            conn.execute("SELECT label_id, artifact_json FROM learning_outcome_labels")
        ):
            raw = json.loads(aj)
            ghost_parent = f"ghost-parent-{i}"
            ghost_label = f"{i:064x}"
            raw["observation_id"] = ghost_parent
            raw["label_id"] = ghost_label
            conn.execute(
                "UPDATE learning_outcome_labels SET observation_id=?, label_id=?, artifact_json=? "
                "WHERE label_id=?",
                (
                    ghost_parent,
                    ghost_label,
                    json.dumps(raw, sort_keys=True, separators=(",", ":")),
                    lid,
                ),
            )
        conn.commit()

    with pytest.raises(LearningArtifactReadIntegrityError):
        GetAccumulationProducerReadinessUseCase(
            observations=repo,
            labels=repo,
            policy_snapshots=repo,
            session_snapshot_lookup=_snapshot_lookup,
        ).execute()


def test_invalid_pre_open_label_does_not_block_accum_status(tmp_path) -> None:
    """Corrupt PRE_OPEN label must not abort ACCUM readiness (purpose isolation)."""
    import sqlite3

    db = tmp_path / "preopen-isolation.db"
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(day=1, compatibility_id=COMPAT_B, ticker="BBCA")
    o2 = _observation(day=2, compatibility_id=COMPAT_B, ticker="BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
        repo.add_label(_label(o))
    _seed_full_v2(repo, COMPAT_B)

    # Insert a PRE_OPEN observation + corrupt PRE_OPEN label (digest mismatch).
    pre_at = datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc)
    pre_obs = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open.v1",
        horizon_contract="open_30m",
        compatibility_id="preopen-compat",
        cutoff_at=pre_at,
        universe_id=UNIVERSE_ID,
        window_id="BBCA:2026-07-05",
        decision_payload={"ticker": "BBCA", "session_date": "2026-07-05"},
        captured_at=pre_at,
        producer_source_revision="ai-saham@test",
    )
    repo.add_observation(pre_obs)
    pre_label = LearningOutcomeLabel.create(
        contract_id=LearningContractId.PRE_OPEN_LABEL,
        observation_id=pre_obs.observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="UP",
        metrics={"return": 0.1},
        fingerprint="fp-preopen",
        labeled_at=NOW,
    )
    repo.add_label(pre_label)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE learning_outcome_labels SET artifact_digest = ? WHERE label_id = ?",
            ("0" * 64, pre_label.label_id),
        )
        conn.commit()

    report = GetAccumulationProducerReadinessUseCase(
        observations=repo,
        labels=repo,
        policy_snapshots=repo,
        session_snapshot_lookup=_snapshot_lookup,
    ).execute()
    # ACCUM cohort still evaluates (PRE_OPEN corruption is isolated).
    assert report.observation_count == 2
    assert report.cohort_count == 1
    assert report.cohorts[0].compatibility_id == COMPAT_B
    assert report.cohorts[0].producer_status is ProducerReadinessStatus.CHALLENGE_INPUT_READY


def test_invalid_accum_label_still_fails_closed(tmp_path) -> None:
    """Corrupt ACCUM label still fails readiness (not purpose-isolated away)."""
    import sqlite3

    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        LearningArtifactReadIntegrityError,
    )

    db = tmp_path / "accum-label-corrupt.db"
    repo = SQLiteLearningArtifactRepository(db)
    o1 = _observation(day=1, compatibility_id=COMPAT_B, ticker="BBCA")
    o2 = _observation(day=2, compatibility_id=COMPAT_B, ticker="BBRI")
    for o in (o1, o2):
        repo.add_observation(o)
        repo.add_label(_label(o))
    _seed_full_v2(repo, COMPAT_B)

    with sqlite3.connect(db) as conn:
        lid = conn.execute("SELECT label_id FROM learning_outcome_labels LIMIT 1").fetchone()[0]
        conn.execute(
            "UPDATE learning_outcome_labels SET artifact_digest = ? WHERE label_id = ?",
            ("0" * 64, lid),
        )
        conn.commit()

    with pytest.raises(LearningArtifactReadIntegrityError):
        GetAccumulationProducerReadinessUseCase(
            observations=repo,
            labels=repo,
            policy_snapshots=repo,
            session_snapshot_lookup=_snapshot_lookup,
        ).execute()
