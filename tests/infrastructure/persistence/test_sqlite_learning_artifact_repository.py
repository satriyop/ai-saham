from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.domain.value_objects.learning_artifacts import (
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
        horizon_contract="accum_20d",
        compatibility_id="compat-1",
        cutoff_at=NOW,
        universe_id="idx30",
        window_id="BBCA:2026-07-27",
        decision_payload={"funnel": "PASS"},
        captured_at=NOW,
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
    }


def test_identical_insert_is_idempotent_and_conflict_fails(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _observation()

    assert repository.add_observation(observation) is True
    assert repository.add_observation(observation) is False

    conflict = replace(observation, artifact_digest="0" * 64)
    with pytest.raises(LearningContractError, match="digest does not match"):
        repository.add_observation(conflict)


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
        contract_id=LearningContractId.ACCUMULATION_LABEL,
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
        contract_id=LearningContractId.ACCUMULATION_LABEL,
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
            contract_id=LearningContractId.ACCUMULATION_LABEL,
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
