"""Normalized-column reconciliation: corrupt shadow columns cannot hide artifacts."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LabelAvailability,
    LearningContractId,
    LearningObservation,
    LearningOutcomeLabel,
    OutcomeBasis,
    ProductionPolicySnapshot,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    LearningArtifactReadIntegrityError,
    SQLiteLearningArtifactReadRepository,
    SQLiteLearningArtifactRepository,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)
MATERIAL = "sha256:" + ("ab" * 32)


def _observation() -> LearningObservation:
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id="compat-1",
        cutoff_at=NOW,
        universe_id="u1",
        window_id="BBCA:2026-07-27",
        decision_payload={"funnel": "PASS"},
        captured_at=NOW,
    )


def _label(observation_id: str, digest: str) -> LearningOutcomeLabel:
    return LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id=observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="UP",
        metrics={"return": 0.1},
        fingerprint="fp-" + digest[:16],
        labeled_at=NOW,
    )


def _policy() -> ProductionPolicySnapshot:
    return ProductionPolicySnapshot.create(
        contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
        producer_observation_contract="accumulation-discovery.v2",
        compatibility_id="compat-1",
        policy_id="screener.accum.score_weights",
        policy_version="v1",
        decision_type="score",
        semantic_engine_contract_id="sem.v1",
        material_config_hash=MATERIAL,
        canonical_payload={
            "policy_id": "screener.accum.score_weights",
            "policy_version": "v1",
            "decision_type": "score",
            "semantic_engine_contract_id": "sem.v1",
        },
        source_revision="test",
        created_at=NOW,
    )


_OBS_MUTATIONS = (
    "purpose",
    "compatibility_id",
    "observation_id",
    "artifact_digest",
    "contract_id",
    "policy_contract",
    "horizon_contract",
    "cutoff_at",
    "universe_id",
    "window_id",
    "decision_payload_json",
    "captured_at",
)


def _obs_corrupt_value(column: str, obs: LearningObservation) -> str:
    if column == "purpose":
        return AssessmentPurpose.SWING_TRADE_SETUP.value  # still satisfies CHECK
    if column == "decision_payload_json":
        return '{"funnel":"MUTATED"}'
    if column == "observation_id":
        return "mutated-obs-id"
    if column == "cutoff_at":
        return "2099-01-01T00:00:00+00:00"
    if column == "captured_at":
        return "2099-01-01T00:00:00+00:00"
    return f"mutated-{column}"


@pytest.mark.parametrize("column", _OBS_MUTATIONS)
def test_observation_column_mutation_raises_integrity(tmp_path: Path, column: str) -> None:
    db = tmp_path / "o.db"
    repo = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    repo.add_observation(obs)
    corrupt = _obs_corrupt_value(column, obs)

    with sqlite3.connect(db) as conn:
        conn.execute(
            f"UPDATE learning_observations SET {column} = ? WHERE observation_id = ?",
            (corrupt, obs.observation_id),
        )
        conn.commit()

    # Corrupt row remains discoverable and fails closed.
    with pytest.raises(LearningArtifactReadIntegrityError):
        list(repo.list_observations(AssessmentPurpose.ACCUMULATION_DISCOVERY))


def test_observation_purpose_drift_still_visible_for_artifact_purpose(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    repo = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    repo.add_observation(obs)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE learning_observations SET purpose = ? WHERE observation_id = ?",
            (AssessmentPurpose.SWING_TRADE_SETUP.value, obs.observation_id),
        )
        conn.commit()
    with pytest.raises(LearningArtifactReadIntegrityError, match="purpose"):
        list(repo.list_observations(AssessmentPurpose.ACCUMULATION_DISCOVERY))


def test_idempotent_insert_rejects_digest_match_with_corrupt_shadow(tmp_path: Path) -> None:
    db = tmp_path / "i.db"
    repo = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    assert repo.add_observation(obs) is True
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE learning_observations SET decision_payload_json = ? WHERE observation_id = ?",
            ('{"funnel": "PASS"}', obs.observation_id),  # non-canonical spacing
        )
        conn.commit()
    with pytest.raises(LearningArtifactReadIntegrityError):
        repo.add_observation(obs)


_LABEL_MUTATIONS = (
    "observation_id",
    "label_id",
    "artifact_digest",
    "contract_id",
    "outcome_basis",
    "availability",
    "metrics_json",
    "fingerprint",
    "labeled_at",
)


def _label_corrupt_value(column: str) -> str:
    if column == "outcome_basis":
        return OutcomeBasis.SIMULATED_NET_EXECUTION.value
    if column == "availability":
        return LabelAvailability.UNAVAILABLE.value
    if column == "metrics_json":
        return '{"return":9}'
    if column == "labeled_at":
        return "2099-01-01T00:00:00+00:00"
    if column == "observation_id":
        return "mutated-parent"
    return f"mutated-{column}"


@pytest.mark.parametrize("column", _LABEL_MUTATIONS)
def test_label_column_mutation_raises_integrity(tmp_path: Path, column: str) -> None:
    db = tmp_path / "l.db"
    repo = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    repo.add_observation(obs)
    label = _label(obs.observation_id, obs.artifact_digest)
    repo.add_label(label)
    corrupt = _label_corrupt_value(column)

    with sqlite3.connect(db) as conn:
        conn.execute(
            f"UPDATE learning_outcome_labels SET {column} = ? WHERE label_id = ?",
            (corrupt, label.label_id),
        )
        conn.commit()

    with pytest.raises(LearningArtifactReadIntegrityError):
        # Dual-key: original parent id still finds row when observation_id column drifts.
        list(repo.list_labels([obs.observation_id, "mutated-parent"]))


_POLICY_MUTATIONS = (
    "purpose",
    "compatibility_id",
    "policy_id",
    "material_config_hash",
    "canonical_payload_json",
    "payload_digest",
    "source_revision",
    "created_at",
)


@pytest.mark.parametrize("column", _POLICY_MUTATIONS)
def test_policy_column_mutation_raises_integrity(tmp_path: Path, column: str) -> None:
    db = tmp_path / "s.db"
    repo = SQLiteLearningArtifactRepository(db)
    snap = _policy()
    repo.add_policy_snapshot(snap)

    with sqlite3.connect(db) as conn:
        if column == "canonical_payload_json":
            conn.execute(
                "UPDATE learning_policy_snapshots SET canonical_payload_json = ? "
                "WHERE snapshot_id = ?",
                ('{"policy_id":"x"}', snap.snapshot_id),
            )
        elif column == "compatibility_id":
            conn.execute(
                "UPDATE learning_policy_snapshots SET compatibility_id = ? WHERE snapshot_id = ?",
                ("mutated-compat", snap.snapshot_id),
            )
        else:
            conn.execute(
                f"UPDATE learning_policy_snapshots SET {column} = ? WHERE snapshot_id = ?",
                ("MUTATED", snap.snapshot_id),
            )
        conn.commit()

    with pytest.raises(LearningArtifactReadIntegrityError):
        list(
            repo.list_policy_snapshots(
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                compatibility_id="compat-1",
            )
        )


def test_read_repository_reconciliation_is_readonly(tmp_path: Path) -> None:
    db = tmp_path / "ro.db"
    write = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    write.add_observation(obs)
    before = db.stat()
    ro = SQLiteLearningArtifactReadRepository(db)
    loaded = list(ro.list_observations(AssessmentPurpose.ACCUMULATION_DISCOVERY))
    after = db.stat()
    assert len(loaded) == 1
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns
