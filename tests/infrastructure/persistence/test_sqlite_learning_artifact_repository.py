from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.value_objects.learning_artifacts import (
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    AssessmentPurpose,
    EvaluationMethod,
    EvaluationReadiness,
    LabelAvailability,
    LearningContractError,
    LearningContractId,
    LearningEvaluation,
    LearningObservation,
    LearningOutcomeLabel,
    LearningPolicyApplication,
    LearningPolicyProposal,
    LearningPolicyValidation,
    LearningTrackSnapshot,
    OutcomeBasis,
    ProductionPolicySnapshot,
    ValidationStatus,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
    connect_learning_database,
)

NOW = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)


def _observation() -> LearningObservation:
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id="compat-1",
        cutoff_at=NOW,
        universe_id="idx30",
        window_id="BBCA:2026-07-27",
        decision_payload={"funnel": "PASS"},
        captured_at=NOW,
        producer_source_revision="ai-saham@test",
    )


def _evaluation(
    *,
    fingerprint: str,
    readiness: EvaluationReadiness = EvaluationReadiness.OOS_DIAGNOSTIC_READY,
) -> LearningEvaluation:
    return LearningEvaluation.create(
        purpose=AssessmentPurpose.SWING_TRADE_SETUP,
        method=EvaluationMethod.PORTFOLIO_WALK_FORWARD,
        compatibility_id="compat-1",
        dataset_fingerprint=fingerprint,
        split_contract="chronological.v1",
        population={"fingerprint": "population-1", "trade_count": 30},
        exclusions={},
        metrics={"net_return": 5.0},
        outcome_basis=OutcomeBasis.SIMULATED_NET_EXECUTION,
        readiness=readiness,
        evaluated_at=NOW,
    )


def _paired_deltas() -> dict[str, float]:
    return {
        "net_return": 1.0,
        "profit_factor": 0.1,
        "average_return": 0.05,
        "drawdown_regression": 0.0,
        "trade_count": 0.0,
        "regime_stability": 0.0,
        "authority_coverage": 0.0,
        "setup_readiness": 0.0,
    }


def test_schema_enables_foreign_keys_and_creates_exact_learning_tables(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data.db"
    SQLiteLearningArtifactRepository(db_path)

    with connect_learning_database(db_path) as connection:
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute("""
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name LIKE 'learning_%'
                """)
        }

    assert enabled == 1
    assert tables == {
        "learning_observations",
        "learning_track_snapshots",
        "learning_outcome_labels",
        "learning_evaluations",
        "learning_policy_proposals",
        "learning_policy_validations",
        "learning_policy_applications",
        "learning_policy_snapshots",
    }


def test_identical_insert_is_idempotent_and_conflict_fails(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _observation()

    assert repository.add_observation(observation) is True
    assert repository.add_observation(observation) is False

    conflict = replace(observation, artifact_digest="0" * 64)
    with pytest.raises(LearningContractError, match="digest does not match"):
        repository.add_observation(conflict)


def test_observation_reuse_tolerates_different_producer_source_revision(
    tmp_path: Path,
) -> None:
    """ADR-068 slice 5: producer_source_revision is provenance in artifact_json.

    Same identity + same digest under a different build reuses the first row
    (artifact_json is already in _OBS_PROVENANCE_COLUMNS).
    """
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    first = _observation()
    second = LearningObservation.create(
        purpose=first.purpose,
        policy_contract=first.policy_contract,
        horizon_contract=first.horizon_contract,
        compatibility_id=first.compatibility_id,
        cutoff_at=first.cutoff_at,
        universe_id=first.universe_id,
        window_id=first.window_id,
        decision_payload=first.decision_payload,
        captured_at=first.captured_at,
        producer_source_revision="ai-saham@a-different-build",
    )
    assert first.observation_id == second.observation_id
    assert first.artifact_digest == second.artifact_digest
    assert first.producer_source_revision != second.producer_source_revision

    assert repository.add_observation(first) is True
    assert repository.add_observation(second) is False
    stored = repository.get_observation(first.observation_id)
    assert stored is not None
    assert stored.producer_source_revision == first.producer_source_revision


def test_observation_digest_still_varies_with_captured_at(tmp_path: Path) -> None:
    """Pins current, deliberately-unchanged behaviour: unlike labels and policy
    snapshots, LearningObservation still digests captured_at (only
    producer_source_revision is excluded per ADR-068 §6). A second
    add_observation for the same content at a different wall-clock time is
    therefore a genuine digest conflict, not the shadow-column mismatch this
    module's other new tests guard against. Production safety for the real
    capture path comes from AccumulationCandidateObservationPersister's own
    pre-existence check (get_observation(...) is not None -> skip) before it
    ever calls add_observation twice for one observation_id — not from this
    repository method being safe to call twice with a drifting captured_at.
    If a future change adds captured_at to DIGEST_EXCLUDED_FIELDS, this test's
    second assertion will start failing and should be updated deliberately,
    not silently.
    """
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    first = _observation()
    second = LearningObservation.create(
        purpose=first.purpose,
        policy_contract=first.policy_contract,
        horizon_contract=first.horizon_contract,
        compatibility_id=first.compatibility_id,
        cutoff_at=first.cutoff_at,
        universe_id=first.universe_id,
        window_id=first.window_id,
        decision_payload=first.decision_payload,
        captured_at=NOW.replace(hour=2),
        producer_source_revision="ai-saham@test",
    )
    # observation_id is identity-derived (purpose/contracts/compatibility_id/
    # cutoff_at/universe_id/window_id) and does not include captured_at.
    assert first.observation_id == second.observation_id
    assert first.artifact_digest != second.artifact_digest

    assert repository.add_observation(first) is True
    with pytest.raises(LearningContractError, match="immutable artifact conflict"):
        repository.add_observation(second)


def test_tracks_and_labels_reject_orphan_observations(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    track = LearningTrackSnapshot.create(
        observation_id="missing",
        sampled_at=NOW,
        source="stockbit.order_book",
        snapshot_payload={"best_bid": 9000},
        captured_at=NOW,
    )
    label = LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id="missing",
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="UP",
        metrics={"return_pct": 2.0},
        fingerprint="prices-1",
        labeled_at=NOW,
    )

    with pytest.raises(Exception, match="FOREIGN KEY"):
        repository.add_track_snapshot(track)
    with pytest.raises(Exception, match="FOREIGN KEY"):
        repository.add_label(label)


def test_round_trip_observation_track_and_label(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _observation()
    repository.add_observation(observation)
    track = LearningTrackSnapshot.create(
        observation_id=observation.observation_id,
        sampled_at=NOW,
        source="stockbit.order_book",
        snapshot_payload={"best_bid": 9000},
        captured_at=NOW,
    )
    label = LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id=observation.observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="UP",
        metrics={"return_pct": 2.0},
        fingerprint="prices-1",
        labeled_at=NOW,
    )

    repository.add_track_snapshot(track)
    repository.add_label(label)

    assert repository.get_observation(observation.observation_id) == observation
    assert repository.list_track_snapshots(observation.observation_id) == (track,)
    assert repository.list_labels([observation.observation_id]) == (label,)


def test_label_reuse_tolerates_different_labeled_at(tmp_path: Path) -> None:
    """Regression: labeled_at is already excluded from LearningOutcomeLabel's
    digest, so a re-run that recomputes the same label content at a different
    wall-clock time must reuse the existing row, not raise on the shadow
    column check.
    """
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _observation()
    repository.add_observation(observation)
    first = LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id=observation.observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="UP",
        metrics={"return_pct": 2.0},
        fingerprint="prices-1",
        labeled_at=NOW,
    )
    second = LearningOutcomeLabel.create(
        contract_id=first.contract_id,
        observation_id=first.observation_id,
        outcome_basis=first.outcome_basis,
        availability=first.availability,
        outcome=first.outcome,
        metrics=first.metrics,
        fingerprint=first.fingerprint,
        labeled_at=NOW.replace(hour=9),
    )
    assert first.label_id == second.label_id
    assert first.artifact_digest == second.artifact_digest
    assert first.labeled_at != second.labeled_at

    assert repository.add_label(first) is True
    assert repository.add_label(second) is False
    assert repository.list_labels([observation.observation_id]) == (first,)


def test_proposal_validation_application_foreign_keys_and_round_trip(
    tmp_path: Path,
) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    baseline = _evaluation(fingerprint="baseline")
    proposed = _evaluation(fingerprint="proposed")
    repository.add_evaluation(baseline)
    repository.add_evaluation(proposed)
    proposal = LearningPolicyProposal.create(
        source_evaluation_id=baseline.evaluation_id,
        current_config_hash="config-before",
        changes={"signal.threshold": 70},
        rationale={"source": "IS attribution"},
        created_at=NOW,
    )
    repository.add_proposal(proposal)
    validation = LearningPolicyValidation.create(
        proposal_id=proposal.proposal_id,
        baseline_evaluation_id=baseline.evaluation_id,
        proposed_evaluation_id=proposed.evaluation_id,
        population_fingerprint="population-1",
        paired_deltas=_paired_deltas(),
        issues=(),
        status=ValidationStatus.PASS,
        validated_at=NOW,
    )
    repository.add_validation(validation)
    application = LearningPolicyApplication.create(
        proposal_id=proposal.proposal_id,
        validation_id=validation.validation_id,
        previous_config_hash="config-before",
        applied_config_hash="config-after",
        exact_changes=proposal.changes,
        confirmation_identity="human:test",
        applied_at=NOW,
        reread_verified=True,
    )
    repository.add_application(application)

    assert repository.get_evaluation(baseline.evaluation_id) == baseline
    assert repository.get_proposal(proposal.proposal_id) == proposal
    assert repository.get_validation_for_proposal(proposal.proposal_id) == validation
    assert repository.get_application_for_proposal(proposal.proposal_id) == application


def test_proposal_rejects_orphan_source_evaluation(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    proposal = LearningPolicyProposal.create(
        source_evaluation_id="missing",
        current_config_hash="config-before",
        changes={"signal.threshold": 70},
        rationale={},
        created_at=NOW,
    )

    with pytest.raises(Exception, match="FOREIGN KEY"):
        repository.add_proposal(proposal)


def test_delete_is_restricted_for_linked_artifacts(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    repository = SQLiteLearningArtifactRepository(db_path)
    observation = _observation()
    repository.add_observation(observation)
    repository.add_label(
        LearningOutcomeLabel.create(
            contract_id=LearningContractId.ACCUM_10D_LABEL,
            observation_id=observation.observation_id,
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            availability=LabelAvailability.UNAVAILABLE,
            outcome=None,
            metrics={},
            fingerprint="prices-missing",
            labeled_at=NOW,
        )
    )

    with connect_learning_database(db_path) as connection:
        with pytest.raises(Exception, match="FOREIGN KEY"):
            connection.execute(
                "DELETE FROM learning_observations WHERE observation_id = ?",
                (observation.observation_id,),
            )


def _policy_snapshot(
    *,
    policy_id: str = PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    weight: float = 33.3,
    compatibility_id: str = "sha256:" + ("ab" * 32),
    contract_id: LearningContractId = LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
) -> ProductionPolicySnapshot:
    return ProductionPolicySnapshot.create(
        contract_id=contract_id,
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
        producer_observation_contract="accumulation-discovery.v2",
        compatibility_id=compatibility_id,
        policy_id=policy_id,
        policy_version="v1",
        decision_type="score",
        semantic_engine_contract_id="accum_score_policy.v1",
        material_config_hash="sha256:" + ("cd" * 32),
        canonical_payload={
            "policy_id": policy_id,
            "policy_version": "v1",
            "decision_type": "score",
            "semantic_engine_contract_id": "accum_score_policy.v1",
            "components": [{"key": "consistency", "enabled": True, "weight": weight}],
        },
        source_revision="ai-saham@test",
        created_at=NOW,
    )


def test_policy_snapshot_round_trip_and_idempotent(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    snap = _policy_snapshot()

    assert repository.add_policy_snapshot(snap) is True
    assert repository.add_policy_snapshot(snap) is False
    loaded = repository.get_policy_snapshot(snap.snapshot_id)
    assert loaded == snap
    by_binding = repository.get_policy_snapshot_by_binding(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        compatibility_id=snap.compatibility_id,
        policy_id=snap.policy_id,
    )
    assert by_binding == snap
    listed = repository.list_policy_snapshots(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        compatibility_id=snap.compatibility_id,
    )
    assert listed == (snap,)


def test_policy_snapshot_reuse_tolerates_different_provenance(tmp_path: Path) -> None:
    """Regression: EnsureAccumulationPolicySnapshotsUseCase calls
    add_policy_snapshots_atomic on every capture, unconditionally, with a
    fresh created_at and the current build's source_revision each time. Under
    a stable cohort the payload is unchanged day to day, so this is the
    designed-for "reused" path (ADR-068 SS6: a cohort spanning several builds
    is expected and reassuring, not an error) -- it must not raise.
    """
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    first = _policy_snapshot()
    second = ProductionPolicySnapshot.create(
        contract_id=first.contract_id,
        purpose=first.purpose,
        learning_observation_contract_id=first.learning_observation_contract_id,
        producer_observation_contract=first.producer_observation_contract,
        compatibility_id=first.compatibility_id,
        policy_id=first.policy_id,
        policy_version=first.policy_version,
        decision_type=first.decision_type,
        semantic_engine_contract_id=first.semantic_engine_contract_id,
        material_config_hash=first.material_config_hash,
        canonical_payload=first.canonical_payload,
        source_revision="ai-saham@a-different-build",
        created_at=NOW.replace(hour=5),
    )
    assert first.snapshot_id == second.snapshot_id
    assert first.payload_digest == second.payload_digest
    assert first.created_at != second.created_at
    assert first.source_revision != second.source_revision

    assert repository.add_policy_snapshot(first) is True
    assert repository.add_policy_snapshot(second) is False
    # First write wins: the stored row keeps the original provenance.
    assert repository.get_policy_snapshot(first.snapshot_id) == first


def test_policy_snapshot_digest_conflict_fails_closed(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    first = _policy_snapshot(weight=33.3)
    second = _policy_snapshot(weight=40.0)
    assert first.snapshot_id == second.snapshot_id
    assert first.payload_digest != second.payload_digest

    assert repository.add_policy_snapshot(first) is True
    with pytest.raises(LearningContractError, match="immutable artifact conflict"):
        repository.add_policy_snapshot(second)


def test_policy_snapshot_atomic_batch_all_or_nothing(tmp_path: Path) -> None:
    from src.domain.value_objects.learning_artifacts import (
        ACCUMULATION_PRODUCTION_POLICY_IDS,
    )

    compat = "sha256:" + ("22" * 32)
    repo = SQLiteLearningArtifactRepository(tmp_path / "atomic.db")
    first = _policy_snapshot(
        policy_id=ACCUMULATION_PRODUCTION_POLICY_IDS[0],
        weight=1.0,
        compatibility_id=compat,
    )
    rest = [
        _policy_snapshot(
            policy_id=pid,
            weight=1.0,
            compatibility_id=compat,
        )
        for pid in ACCUMULATION_PRODUCTION_POLICY_IDS[1:]
    ]
    twin = _policy_snapshot(
        policy_id=ACCUMULATION_PRODUCTION_POLICY_IDS[0],
        weight=2.0,
        compatibility_id=compat,
    )
    assert first.snapshot_id == twin.snapshot_id
    assert first.payload_digest != twin.payload_digest

    # Duplicate snapshot_id with different digest in one batch: preflight rejects
    # before any write, so the cohort remains empty.
    with pytest.raises(LearningContractError, match="duplicate snapshot_id"):
        repo.add_policy_snapshots_atomic([first, *rest, twin])
    assert (
        repo.list_policy_snapshots(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id=compat,
        )
        == ()
    )

    # Happy path: closed seven-row v2 set in one transaction.
    inserted, reused = repo.add_policy_snapshots_atomic([first, *rest])
    assert inserted == 7
    assert reused == 0
    assert (
        len(
            repo.list_policy_snapshots(
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                compatibility_id=compat,
            )
        )
        == 7
    )

    # Idempotent atomic re-run reuses all seven.
    inserted2, reused2 = repo.add_policy_snapshots_atomic([first, *rest])
    assert inserted2 == 0
    assert reused2 == 7

    # Mid-batch conflict against existing rows rolls back: no extra rows, no
    # mutation. Seed a second cohort then fail a mixed batch that collides.
    compat_b = "sha256:" + ("33" * 32)
    new_rows = [
        _policy_snapshot(policy_id=pid, weight=1.0, compatibility_id=compat_b)
        for pid in ACCUMULATION_PRODUCTION_POLICY_IDS
    ]
    # Conflict: include twin of already-stored first snapshot (compat A).
    with pytest.raises(LearningContractError, match="immutable artifact conflict"):
        repo.add_policy_snapshots_atomic([*new_rows, twin])
    # New cohort must not partially appear.
    assert (
        repo.list_policy_snapshots(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id=compat_b,
        )
        == ()
    )
    # Original cohort intact.
    assert (
        len(
            repo.list_policy_snapshots(
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                compatibility_id=compat,
            )
        )
        == 7
    )


def test_policy_snapshot_v3_migration_preserves_v1_and_accepts_v2(tmp_path: Path) -> None:
    """Existing v1-only CHECK tables must rebuild under migration version 3."""
    import sqlite3

    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        LEARNING_MIGRATION_NAMESPACE,
        ensure_learning_schema,
    )

    db_path = tmp_path / "legacy_v1_check.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE _schema_migrations (
            namespace TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (namespace, version)
        )
        """
    )
    # Pre-v3 table: v1-only contract CHECK (the defect migration 3 fixes).
    conn.execute(
        """
        CREATE TABLE learning_policy_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL CHECK (schema_version = 1),
            contract_id TEXT NOT NULL CHECK (contract_id = 'production_policy_snapshot.v1'),
            purpose TEXT NOT NULL,
            learning_observation_contract_id TEXT NOT NULL,
            producer_observation_contract TEXT NOT NULL,
            compatibility_id TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            policy_version TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            semantic_engine_contract_id TEXT NOT NULL,
            material_config_hash TEXT NOT NULL,
            canonical_payload_json TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            created_at TEXT NOT NULL,
            artifact_json TEXT NOT NULL,
            UNIQUE (purpose, compatibility_id, policy_id)
        )
        """
    )
    from dataclasses import asdict

    from src.domain.value_objects.learning_artifacts import canonical_json

    legacy = _policy_snapshot(
        contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1,
        compatibility_id="sha256:" + ("aa" * 32),
        weight=10.0,
    )
    conn.execute(
        """
        INSERT INTO learning_policy_snapshots (
            snapshot_id, schema_version, contract_id, purpose,
            learning_observation_contract_id, producer_observation_contract,
            compatibility_id, policy_id, policy_version, decision_type,
            semantic_engine_contract_id, material_config_hash,
            canonical_payload_json, payload_digest, source_revision,
            created_at, artifact_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            legacy.snapshot_id,
            legacy.schema_version,
            legacy.contract_id.value,
            legacy.purpose.value,
            legacy.learning_observation_contract_id,
            legacy.producer_observation_contract,
            legacy.compatibility_id,
            legacy.policy_id,
            legacy.policy_version,
            legacy.decision_type,
            legacy.semantic_engine_contract_id,
            legacy.material_config_hash,
            canonical_json(legacy.canonical_payload),
            legacy.payload_digest,
            legacy.source_revision,
            legacy.created_at.isoformat(),
            canonical_json(asdict(legacy)),
        ),
    )
    conn.execute(
        "INSERT INTO _schema_migrations(namespace, version) VALUES (?, 1)",
        (LEARNING_MIGRATION_NAMESPACE,),
    )
    conn.execute(
        "INSERT INTO _schema_migrations(namespace, version) VALUES (?, 2)",
        (LEARNING_MIGRATION_NAMESPACE,),
    )
    conn.commit()
    # Prove pre-migration CHECK rejects v2.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO learning_policy_snapshots (
                snapshot_id, schema_version, contract_id, purpose,
                learning_observation_contract_id, producer_observation_contract,
                compatibility_id, policy_id, policy_version, decision_type,
                semantic_engine_contract_id, material_config_hash,
                canonical_payload_json, payload_digest, source_revision,
                created_at, artifact_json
            ) VALUES (?, 1, 'production_policy_snapshot.v2', 'ACCUMULATION_DISCOVERY',
                      'c', 'p', 'compat', 'pid', 'v1', 'score', 's', 'h', '{}',
                      ?, 'rev', '2026-01-01T00:00:00+00:00', '{}')
            """,
            ("x", "0" * 64),
        )
    conn.close()

    ensure_learning_schema(db_path)
    with connect_learning_database(db_path) as connection:
        versions = {
            int(r[0])
            for r in connection.execute(
                "SELECT version FROM _schema_migrations WHERE namespace = ?",
                (LEARNING_MIGRATION_NAMESPACE,),
            ).fetchall()
        }
        assert 3 in versions
        count = connection.execute("SELECT COUNT(*) FROM learning_policy_snapshots").fetchone()[0]
        assert count == 1
        row = connection.execute(
            "SELECT contract_id, payload_digest FROM learning_policy_snapshots"
        ).fetchone()
        assert row["contract_id"] == "production_policy_snapshot.v1"
        assert row["payload_digest"] == legacy.payload_digest

    repo = SQLiteLearningArtifactRepository(db_path)
    v2 = _policy_snapshot(
        contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
        compatibility_id="sha256:" + ("bb" * 32),
        weight=11.0,
    )
    assert repo.add_policy_snapshot(v2) is True
    loaded = repo.get_policy_snapshot(v2.snapshot_id)
    assert loaded is not None
    assert loaded.contract_id is LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2
    # Historical v1 row still present under its compatibility id.
    listed_v1 = repo.list_policy_snapshots(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        compatibility_id=legacy.compatibility_id,
    )
    assert len(listed_v1) == 1
    assert listed_v1[0].snapshot_id == legacy.snapshot_id


def test_v1_and_v2_snapshots_coexist_under_different_compatibility_ids(
    tmp_path: Path,
) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "coexist.db")
    v1 = _policy_snapshot(
        contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1,
        compatibility_id="sha256:" + ("11" * 32),
    )
    v2 = _policy_snapshot(
        contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
        compatibility_id="sha256:" + ("22" * 32),
    )
    assert repo.add_policy_snapshot(v1) is True
    assert repo.add_policy_snapshot(v2) is True
    assert repo.get_policy_snapshot(v1.snapshot_id) == v1
    assert repo.get_policy_snapshot(v2.snapshot_id) == v2
