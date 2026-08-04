"""SQLite repair for legacy labeled_at label digests."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LabelAvailability,
    LearningContractId,
    LearningObservation,
    LearningOutcomeLabel,
    OutcomeBasis,
    artifact_digest,
    modern_label_digest,
)
from src.infrastructure.persistence.legacy_label_digest_repair import (
    repair_legacy_labeled_at_label_digests,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

NOW = datetime(2026, 7, 29, 11, 12, 23, tzinfo=timezone.utc)


def _seed_legacy_label(db: Path) -> LearningOutcomeLabel:
    repo = SQLiteLearningArtifactRepository(db)
    obs = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="sha256:" + ("ab" * 32),
        cutoff_at=NOW,
        universe_id="movers",
        window_id="PADI:2026-07-29",
        decision_payload={"ticker": "PADI"},
        captured_at=NOW,
    )
    assert repo.add_observation(obs) is True
    modern = LearningOutcomeLabel.create(
        contract_id=LearningContractId.PRE_OPEN_LABEL,
        observation_id=obs.observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="FAILURE",
        metrics={"ticker": "PADI", "open_to_close_return_pct": -1.3},
        fingerprint="fp",
        labeled_at=NOW,
    )
    assert repo.add_label(modern) is True
    # Corrupt to pre-11bfca95 digest (include labeled_at in hash).
    payload = asdict(modern)
    payload.pop("label_id")
    payload.pop("artifact_digest")
    legacy = replace(modern, artifact_digest=artifact_digest(payload))
    from src.domain.value_objects.learning_artifacts import canonical_json

    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            """
            UPDATE learning_outcome_labels
            SET artifact_digest = ?, artifact_json = ?
            WHERE label_id = ?
            """,
            (
                legacy.artifact_digest,
                canonical_json(asdict(legacy)),
                legacy.label_id,
            ),
        )
    return legacy


def test_repair_dry_run_does_not_write(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    legacy = _seed_legacy_label(db)
    result = repair_legacy_labeled_at_label_digests(db, dry_run=True)
    assert result.legacy_count == 1
    assert result.repaired_count == 1
    assert result.dry_run is True
    with sqlite3.connect(str(db)) as conn:
        stored = conn.execute(
            "SELECT artifact_digest FROM learning_outcome_labels WHERE label_id = ?",
            (legacy.label_id,),
        ).fetchone()[0]
    assert stored == legacy.artifact_digest


def test_repair_apply_makes_list_labels_work(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    legacy = _seed_legacy_label(db)
    repo = SQLiteLearningArtifactRepository(db)
    try:
        repo.list_labels([legacy.observation_id])
        raised = False
    except Exception:
        raised = True
    assert raised

    result = repair_legacy_labeled_at_label_digests(db, dry_run=False)
    assert result.repaired_count == 1
    assert result.dry_run is False

    labels = repo.list_labels([legacy.observation_id])
    assert len(labels) == 1
    assert labels[0].artifact_digest == modern_label_digest(labels[0])
    assert labels[0].outcome == "FAILURE"
    again = repair_legacy_labeled_at_label_digests(db, dry_run=False)
    assert again.legacy_count == 0
    assert again.already_modern_count >= 1
