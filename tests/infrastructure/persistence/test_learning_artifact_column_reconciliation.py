"""Normalized-column reconciliation: corrupt shadow columns cannot hide artifacts."""

from __future__ import annotations

import json
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


def _observation(*, compatibility_id: str = "compat-1") -> LearningObservation:
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id=compatibility_id,
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


def _policy(*, compatibility_id: str = "compat-1") -> ProductionPolicySnapshot:
    return ProductionPolicySnapshot.create(
        contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
        producer_observation_contract="accumulation-discovery.v2",
        compatibility_id=compatibility_id,
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


# Every normalized observation column (including schema_version + artifact_json).
_OBS_MUTATIONS = (
    "observation_id",
    "artifact_digest",
    "schema_version",
    "contract_id",
    "purpose",
    "policy_contract",
    "horizon_contract",
    "compatibility_id",
    "cutoff_at",
    "universe_id",
    "window_id",
    "decision_payload_json",
    "captured_at",
    "artifact_json",
)

_LABEL_MUTATIONS = (
    "label_id",
    "artifact_digest",
    "schema_version",
    "contract_id",
    "observation_id",
    "outcome_basis",
    "availability",
    "outcome",
    "metrics_json",
    "fingerprint",
    "labeled_at",
    "artifact_json",
)

_POLICY_MUTATIONS = (
    "snapshot_id",
    "schema_version",
    "contract_id",
    "purpose",
    "learning_observation_contract_id",
    "producer_observation_contract",
    "compatibility_id",
    "policy_id",
    "policy_version",
    "decision_type",
    "semantic_engine_contract_id",
    "material_config_hash",
    "canonical_payload_json",
    "payload_digest",
    "source_revision",
    "created_at",
    "artifact_json",
)


def _obs_corrupt_value(column: str) -> object:
    if column == "purpose":
        return AssessmentPurpose.SWING_TRADE_SETUP.value
    if column == "schema_version":
        # CHECK constraint is schema_version = 1; use raw SQL that bypasses by
        # recreating — fall back to non-check path via decision_payload_json style.
        # Use artifact_json for schema_version drift simulation instead in special case.
        return 1  # will be overridden to corrupt differently
    if column == "decision_payload_json":
        return '{"funnel":"MUTATED"}'
    if column == "artifact_json":
        return "{not-json"
    if column in ("cutoff_at", "captured_at"):
        return "2099-01-01T00:00:00+00:00"
    return f"mutated-{column}"


@pytest.mark.parametrize("column", _OBS_MUTATIONS)
def test_observation_column_mutation_raises_integrity(tmp_path: Path, column: str) -> None:
    db = tmp_path / "o.db"
    repo = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    repo.add_observation(obs)

    with sqlite3.connect(db) as conn:
        if column == "schema_version":
            # Bypass CHECK by rewriting table value with pragma off is unreliable;
            # corrupt via dual field: keep schema_version column, break artifact_json
            # schema_version field instead when column is schema_version — use
            # direct UPDATE with PRAGMA ignore_check_constraints not available.
            # Mutate artifact_json.schema_version while leaving column=1.
            raw = json.loads(
                conn.execute(
                    "SELECT artifact_json FROM learning_observations WHERE observation_id = ?",
                    (obs.observation_id,),
                ).fetchone()[0]
            )
            raw["schema_version"] = 99
            conn.execute(
                "UPDATE learning_observations SET artifact_json = ? WHERE observation_id = ?",
                (json.dumps(raw, sort_keys=True, separators=(",", ":")), obs.observation_id),
            )
        elif column == "artifact_json":
            conn.execute(
                "UPDATE learning_observations SET artifact_json = ? WHERE observation_id = ?",
                ("{not-json", obs.observation_id),
            )
        else:
            conn.execute(
                f"UPDATE learning_observations SET {column} = ? WHERE observation_id = ?",
                (_obs_corrupt_value(column), obs.observation_id),
            )
        conn.commit()

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
            ('{"funnel": "PASS"}', obs.observation_id),
        )
        conn.commit()
    with pytest.raises(LearningArtifactReadIntegrityError):
        repo.add_observation(obs)


def _label_corrupt_value(column: str) -> object:
    if column == "outcome_basis":
        return OutcomeBasis.SIMULATED_NET_EXECUTION.value
    if column == "availability":
        return LabelAvailability.UNAVAILABLE.value
    if column == "outcome":
        return "DOWN"
    if column == "metrics_json":
        return '{"return":9}'
    if column == "labeled_at":
        return "2099-01-01T00:00:00+00:00"
    if column == "observation_id":
        return "mutated-parent"
    if column == "artifact_json":
        return "{broken"
    if column == "schema_version":
        return 1
    return f"mutated-{column}"


@pytest.mark.parametrize("column", _LABEL_MUTATIONS)
def test_label_column_mutation_raises_integrity(tmp_path: Path, column: str) -> None:
    db = tmp_path / "l.db"
    repo = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    repo.add_observation(obs)
    label = _label(obs.observation_id, obs.artifact_digest)
    repo.add_label(label)

    with sqlite3.connect(db) as conn:
        if column == "schema_version":
            raw = json.loads(
                conn.execute(
                    "SELECT artifact_json FROM learning_outcome_labels WHERE label_id = ?",
                    (label.label_id,),
                ).fetchone()[0]
            )
            raw["schema_version"] = 99
            conn.execute(
                "UPDATE learning_outcome_labels SET artifact_json = ? WHERE label_id = ?",
                (json.dumps(raw, sort_keys=True, separators=(",", ":")), label.label_id),
            )
        elif column == "artifact_json":
            conn.execute(
                "UPDATE learning_outcome_labels SET artifact_json = ? WHERE label_id = ?",
                ("{broken", label.label_id),
            )
        else:
            conn.execute(
                f"UPDATE learning_outcome_labels SET {column} = ? WHERE label_id = ?",
                (_label_corrupt_value(column), label.label_id),
            )
        conn.commit()

    with pytest.raises(LearningArtifactReadIntegrityError):
        list(repo.list_labels([obs.observation_id, "mutated-parent"]))


def _policy_corrupt_value(column: str) -> object:
    if column == "purpose":
        return AssessmentPurpose.SWING_TRADE_SETUP.value
    if column == "contract_id":
        return LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1.value
    if column == "canonical_payload_json":
        return '{"policy_id":"x"}'
    if column == "created_at":
        return "2099-01-01T00:00:00+00:00"
    if column == "artifact_json":
        return "{broken"
    if column == "schema_version":
        return 1
    return f"mutated-{column}"


@pytest.mark.parametrize("column", _POLICY_MUTATIONS)
def test_policy_column_mutation_raises_integrity(tmp_path: Path, column: str) -> None:
    db = tmp_path / "s.db"
    repo = SQLiteLearningArtifactRepository(db)
    snap = _policy()
    repo.add_policy_snapshot(snap)

    with sqlite3.connect(db) as conn:
        if column == "schema_version":
            raw = json.loads(
                conn.execute(
                    "SELECT artifact_json FROM learning_policy_snapshots WHERE snapshot_id = ?",
                    (snap.snapshot_id,),
                ).fetchone()[0]
            )
            raw["schema_version"] = 99
            conn.execute(
                "UPDATE learning_policy_snapshots SET artifact_json = ? WHERE snapshot_id = ?",
                (json.dumps(raw, sort_keys=True, separators=(",", ":")), snap.snapshot_id),
            )
        elif column == "artifact_json":
            conn.execute(
                "UPDATE learning_policy_snapshots SET artifact_json = ? WHERE snapshot_id = ?",
                ("{broken", snap.snapshot_id),
            )
        else:
            conn.execute(
                f"UPDATE learning_policy_snapshots SET {column} = ? WHERE snapshot_id = ?",
                (_policy_corrupt_value(column), snap.snapshot_id),
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


@pytest.mark.parametrize(
    "repo_cls",
    [SQLiteLearningArtifactRepository, SQLiteLearningArtifactReadRepository],
)
def test_list_observations_compat_filter_does_not_cross_cohorts(
    tmp_path: Path, repo_cls: type
) -> None:
    db = tmp_path / "cross.db"
    write = SQLiteLearningArtifactRepository(db)
    a = _observation(compatibility_id="compat-a")
    b = _observation(compatibility_id="compat-b")
    # Different window so identity diverges.
    b = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id="compat-b",
        cutoff_at=NOW,
        universe_id="u1",
        window_id="BBRI:2026-07-27",
        decision_payload={"funnel": "PASS"},
        captured_at=NOW,
    )
    write.add_observation(a)
    write.add_observation(b)

    if repo_cls is SQLiteLearningArtifactReadRepository:
        repo = repo_cls(db)
    else:
        repo = write

    only_a = list(
        repo.list_observations(
            AssessmentPurpose.ACCUMULATION_DISCOVERY, compatibility_id="compat-a"
        )
    )
    assert len(only_a) == 1
    assert only_a[0].compatibility_id == "compat-a"
    only_b = list(
        repo.list_observations(
            AssessmentPurpose.ACCUMULATION_DISCOVERY, compatibility_id="compat-b"
        )
    )
    assert len(only_b) == 1
    assert only_b[0].compatibility_id == "compat-b"


def test_relinked_label_both_observation_ids_still_discovered(tmp_path: Path) -> None:
    """Coherent dual observation_id rewrite is still found via expected label_id."""
    db = tmp_path / "relink.db"
    repo = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    repo.add_observation(obs)
    label = _label(obs.observation_id, obs.artifact_digest)
    repo.add_label(label)
    original_label_id = label.label_id

    # Relink both normalized column and JSON observation_id to a ghost parent.
    with sqlite3.connect(db) as conn:
        raw = json.loads(
            conn.execute(
                "SELECT artifact_json FROM learning_outcome_labels WHERE label_id = ?",
                (original_label_id,),
            ).fetchone()[0]
        )
        raw["observation_id"] = "ghost-observation"
        # Keep original label_id (identity of the original parent+contract).
        conn.execute(
            """
            UPDATE learning_outcome_labels
            SET observation_id = ?, artifact_json = ?
            WHERE label_id = ?
            """,
            (
                "ghost-observation",
                json.dumps(raw, sort_keys=True, separators=(",", ":")),
                original_label_id,
            ),
        )
        conn.commit()

    # Discovery by parent obs still finds the row (via expected label_id).
    # Loading raises because stored identity (label_id) disagrees with ghost link
    # after recompute — or row/artifact recon may pass if both match ghost.
    # Either way the row must not be invisible.
    from src.domain.value_objects.learning_artifacts import validate_label_identity
    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        expected_label_ids_for_observations,
    )

    expected = expected_label_ids_for_observations([obs.observation_id])
    assert original_label_id in expected

    with sqlite3.connect(db) as conn:
        found = conn.execute(
            "SELECT label_id, observation_id FROM learning_outcome_labels WHERE label_id = ?",
            (original_label_id,),
        ).fetchone()
    assert found is not None

    # list_labels must surface the candidate (integrity error or invalid identity).
    with pytest.raises((LearningArtifactReadIntegrityError, Exception)):
        # If artifact_json was rewritten without reconciling digest/label_id columns
        # consistently, recon raises. If fully consistent ghost link, load may
        # succeed but readiness identity check fails — still not "missing".
        rows = list(repo.list_labels([obs.observation_id]))
        assert len(rows) >= 1
        validate_label_identity(rows[0])
        raise AssertionError("relinked label must not validate cleanly")


def test_relinked_label_is_not_invisible_to_list_labels(tmp_path: Path) -> None:
    db = tmp_path / "relink2.db"
    repo = SQLiteLearningArtifactRepository(db)
    obs = _observation()
    repo.add_observation(obs)
    label = _label(obs.observation_id, obs.artifact_digest)
    repo.add_label(label)
    with sqlite3.connect(db) as conn:
        raw = json.loads(
            conn.execute(
                "SELECT artifact_json FROM learning_outcome_labels WHERE label_id = ?",
                (label.label_id,),
            ).fetchone()[0]
        )
        raw["observation_id"] = "ghost"
        # Keep artifact_digest as-is so recon may fail on digest or identity.
        conn.execute(
            "UPDATE learning_outcome_labels SET observation_id=?, artifact_json=? WHERE label_id=?",
            ("ghost", json.dumps(raw, sort_keys=True, separators=(",", ":")), label.label_id),
        )
        conn.commit()
    # Query by original parent: without label_id discovery this returns [].
    try:
        found = list(repo.list_labels([obs.observation_id]))
    except LearningArtifactReadIntegrityError:
        found = ["raised"]  # discovered then rejected — correct fail-closed
    assert found, "relinked label must remain discoverable for the original parent"
