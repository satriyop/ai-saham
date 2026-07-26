from datetime import datetime, timedelta, timezone

import pytest

from src.application.use_case.swing_policy_learning_use_case import (
    ApplySwingPolicyRequest,
    ApplySwingPolicyUseCase,
    RunSwingPolicyReviewRequest,
    RunSwingPolicyReviewUseCase,
    SwingLearningDataset,
    SwingLearningRow,
    SwingPolicyMetrics,
    SwingPolicySnapshot,
    _population_fingerprint,
)
from src.domain.value_objects.learning_artifacts import (
    EvaluationReadiness,
    LearningContractError,
    ValidationStatus,
    artifact_digest,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)


class RecordingEvaluator:
    def __init__(self) -> None:
        self.policies = []

    def evaluate(self, rows, policy):
        self.policies.append(dict(policy))
        improved = policy.get("threshold") == 60
        return SwingPolicyMetrics(
            population_fingerprint=_population_fingerprint(rows),
            net_return=12.0 if improved else 10.0,
            profit_factor=1.7 if improved else 1.5,
            average_return=1.2 if improved else 1.0,
            max_drawdown=4.0 if improved else 5.0,
            trade_count=12,
            regime_stability=0.8,
            authority_coverage=0.9,
            setup_readiness=0.85,
        )

class ISOnlyProposalGenerator:
    def __init__(self) -> None:
        self.received = None

    def generate(self, is_evaluation):
        self.received = is_evaluation
        assert is_evaluation.population["role"] == "IS_BASELINE"
        return {"threshold": 60}


def _dataset() -> SwingLearningDataset:
    rows = tuple(
        SwingLearningRow(
            row_id=f"row-{index}",
            observed_at=NOW + timedelta(days=index),
            payload={"return": index},
        )
        for index in range(10)
    )
    return SwingLearningDataset(
        compatibility_id="swing-compat-1",
        dataset_fingerprint=artifact_digest(
            {"row_ids": [row.row_id for row in rows]}
        ),
        rows=rows,
    )


def test_emitted_proposal_is_exact_policy_consumed_by_oos_validator(tmp_path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    evaluator = RecordingEvaluator()
    generator = ISOnlyProposalGenerator()

    result = RunSwingPolicyReviewUseCase(
        evaluator=evaluator,
        proposal_generator=generator,
        evaluations=repository,
        proposals=repository,
        validations=repository,
    ).execute(
        RunSwingPolicyReviewRequest(
            dataset=_dataset(),
            baseline_policy=SwingPolicySnapshot(
                config_hash="before",
                values={"threshold": 70},
            ),
            is_ratio=0.7,
            evaluated_at=NOW,
        )
    )

    assert generator.received == result.is_evaluation
    assert result.proposal.changes == {"threshold": 60}
    assert evaluator.policies == [
        {"threshold": 70},
        {"threshold": 70},
        {"threshold": 60},
    ]
    assert (
        result.baseline_oos_evaluation.population["population_fingerprint"]
        == result.proposed_oos_evaluation.population["population_fingerprint"]
    )
    assert result.validation.status is ValidationStatus.PASS
    assert (
        result.proposed_oos_evaluation.readiness
        is EvaluationReadiness.POLICY_REVIEW_ELIGIBLE
    )


def test_evaluator_cannot_substitute_oos_population(tmp_path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")

    class BadEvaluator(RecordingEvaluator):
        def evaluate(self, rows, policy):
            metrics = super().evaluate(rows, policy)
            if len(self.policies) == 2:
                return SwingPolicyMetrics(
                    **{
                        **metrics.__dict__,
                        "population_fingerprint": "substituted",
                    }
                )
            return metrics

    with pytest.raises(LearningContractError, match="changed the immutable population"):
        RunSwingPolicyReviewUseCase(
            evaluator=BadEvaluator(),
            proposal_generator=ISOnlyProposalGenerator(),
            evaluations=repository,
            proposals=repository,
            validations=repository,
        ).execute(
            RunSwingPolicyReviewRequest(
                dataset=_dataset(),
                baseline_policy=SwingPolicySnapshot(
                    config_hash="before",
                    values={"threshold": 70},
                ),
                is_ratio=0.7,
                evaluated_at=NOW,
            )
        )


class MemoryConfigGateway:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.clean = True

    def read_snapshot(self):
        return self.snapshot

    def target_files_clean(self, changes):
        return self.clean

    def apply_changes(self, changes):
        values = {**self.snapshot.values, **changes}
        self.snapshot = SwingPolicySnapshot(
            config_hash=artifact_digest(values),
            values=values,
        )


def test_application_requires_confirmation_and_reread_verification(tmp_path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    review = RunSwingPolicyReviewUseCase(
        evaluator=RecordingEvaluator(),
        proposal_generator=ISOnlyProposalGenerator(),
        evaluations=repository,
        proposals=repository,
        validations=repository,
    ).execute(
        RunSwingPolicyReviewRequest(
            dataset=_dataset(),
            baseline_policy=SwingPolicySnapshot(
                config_hash="before",
                values={"threshold": 70},
            ),
            is_ratio=0.7,
            evaluated_at=NOW,
        )
    )
    gateway = MemoryConfigGateway(
        SwingPolicySnapshot(config_hash="before", values={"threshold": 70})
    )
    use_case = ApplySwingPolicyUseCase(
        proposals=repository,
        validations=repository,
        applications=repository,
        config_gateway=gateway,
    )

    with pytest.raises(LearningContractError, match="explicit --yes"):
        use_case.execute(
            ApplySwingPolicyRequest(
                proposal_id=review.proposal.proposal_id,
                confirmed=False,
                confirmation_identity="human:test",
                applied_at=NOW,
            )
        )

    application = use_case.execute(
        ApplySwingPolicyRequest(
            proposal_id=review.proposal.proposal_id,
            confirmed=True,
            confirmation_identity="human:test",
            applied_at=NOW,
        )
    )

    assert application.reread_verified is True
    with pytest.raises(LearningContractError, match="already been applied"):
        use_case.execute(
            ApplySwingPolicyRequest(
                proposal_id=review.proposal.proposal_id,
                confirmed=True,
                confirmation_identity="human:test",
                applied_at=NOW,
            )
        )
