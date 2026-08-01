from datetime import datetime, timezone

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
    OutcomeBasis,
    ValidationStatus,
    stable_learning_id,
)

NOW = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)


def _observation(*, captured_at: datetime = NOW) -> LearningObservation:
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id="compat-1",
        cutoff_at=NOW,
        universe_id="idx30",
        window_id="BBCA:2026-07-27",
        decision_payload={"funnel": "PASS", "score": 72.0},
        captured_at=captured_at,
    )


def test_observation_id_is_deterministic_and_excludes_captured_at() -> None:
    later = datetime(2026, 7, 27, 2, 0, tzinfo=timezone.utc)

    assert _observation().observation_id == _observation(captured_at=later).observation_id


def test_identity_rejects_captured_at() -> None:
    with pytest.raises(LearningContractError, match="must not participate"):
        stable_learning_id(
            LearningContractId.ACCUMULATION_OBSERVATION,
            {"captured_at": NOW},
        )


@pytest.mark.parametrize(
    ("enum_type", "removed"),
    [
        (AssessmentPurpose, "SIGNAL_COHORT"),
        (EvaluationMethod, "SIGNAL_COHORT"),
        (OutcomeBasis, "raw_market"),
        (OutcomeBasis, "executable"),
    ],
)
def test_removed_contract_names_are_rejected(enum_type: type, removed: str) -> None:
    with pytest.raises(ValueError):
        enum_type(removed)


def test_price_path_evaluation_cannot_be_policy_review_eligible() -> None:
    with pytest.raises(LearningContractError, match="PRICE_PATH_ONLY"):
        LearningEvaluation.create(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            method=EvaluationMethod.FORWARD_OUTCOME_COHORT,
            compatibility_id="compat-1",
            dataset_fingerprint="dataset-1",
            split_contract="chronological.v1",
            population={"observation_ids": [_observation().observation_id]},
            exclusions={},
            metrics={"average_return": 1.2},
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            readiness=EvaluationReadiness.POLICY_REVIEW_ELIGIBLE,
            evaluated_at=NOW,
        )


def test_purpose_and_evaluation_method_are_separate_and_compatible() -> None:
    with pytest.raises(LearningContractError, match="incompatible"):
        LearningEvaluation.create(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            method=EvaluationMethod.PORTFOLIO_WALK_FORWARD,
            compatibility_id="compat-1",
            dataset_fingerprint="dataset-1",
            split_contract="chronological.v1",
            population={"sessions": 2},
            exclusions={},
            metrics={},
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            readiness=EvaluationReadiness.DESCRIPTIVE_READY,
            evaluated_at=NOW,
        )


def test_available_label_requires_outcome() -> None:
    with pytest.raises(LearningContractError, match="requires an outcome"):
        LearningOutcomeLabel.create(
            contract_id=LearningContractId.ACCUM_10D_LABEL,
            observation_id=_observation().observation_id,
            outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
            availability=LabelAvailability.AVAILABLE,
            outcome=None,
            metrics={},
            fingerprint="fingerprint",
            labeled_at=NOW,
        )


def test_label_digest_excludes_labeled_at() -> None:
    """Wall-clock labeled_at is audit-only; re-runs must not change digest."""
    obs_id = _observation().observation_id
    kwargs = dict(
        contract_id=LearningContractId.PRE_OPEN_LABEL,
        observation_id=obs_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="SUCCESS",
        metrics={"open_to_close_return_pct": 0.5},
        fingerprint="tracks-1",
    )
    a = LearningOutcomeLabel.create(**kwargs, labeled_at=NOW)
    b = LearningOutcomeLabel.create(
        **kwargs, labeled_at=datetime(2026, 7, 28, 9, 36, tzinfo=timezone.utc)
    )
    assert a.label_id == b.label_id
    assert a.artifact_digest == b.artifact_digest
    assert a.labeled_at != b.labeled_at


def test_validation_status_values_are_strict() -> None:
    assert ValidationStatus("PASS") is ValidationStatus.PASS
    with pytest.raises(ValueError):
        ValidationStatus("ELIGIBLE")


def test_observation_identity_recompute_detects_forged_id() -> None:
    from dataclasses import replace

    from src.domain.value_objects.learning_artifacts import (
        recompute_observation_id,
        validate_observation_identity,
    )

    obs = _observation()
    validate_observation_identity(obs)
    forged = replace(obs, observation_id="0" * 64)
    with pytest.raises(LearningContractError, match="observation_id"):
        validate_observation_identity(forged)
    assert recompute_observation_id(obs) == obs.observation_id


def test_label_identity_recompute_detects_forged_id() -> None:
    from dataclasses import replace

    from src.domain.value_objects.learning_artifacts import (
        recompute_label_id,
        validate_label_identity,
    )

    label = LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id=_observation().observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="SUCCESS",
        metrics={},
        fingerprint="fp",
        labeled_at=NOW,
    )
    validate_label_identity(label)
    forged = replace(label, label_id="0" * 64)
    with pytest.raises(LearningContractError, match="label_id"):
        validate_label_identity(forged)
    assert recompute_label_id(label) == label.label_id


def test_stamp_universe_membership_id_is_locked_population_authority() -> None:
    """Write-path membership digest is the ACCUM population authority contract."""
    from src.domain.value_objects.learning_artifacts import (
        ACCUM_POPULATION_AUTHORITY_CONTRACT,
        artifact_digest,
        is_accum_population_universe_id,
        stamp_universe_membership_id,
    )

    assert ACCUM_POPULATION_AUTHORITY_CONTRACT == "capture_universe_membership_digest.v1"
    tickers = ["TLKM", "BBCA", "BBRI"]
    stamped = stamp_universe_membership_id(tickers)
    # Same inputs → same population identity (sorted membership).
    assert stamped == stamp_universe_membership_id(["BBCA", "BBRI", "TLKM"])
    assert stamped == artifact_digest({"tickers": sorted(tickers)})
    assert is_accum_population_universe_id(stamped)
    assert type(stamped) is str
    assert len(stamped) == 64
    # Inventable free text is never accepted as authority.
    for free in ("made-up-population", "another-population", "lq45@pit", "idx30"):
        assert not is_accum_population_universe_id(free)
    # No string/float coercion into authority.
    assert not is_accum_population_universe_id("")  # type: ignore[arg-type]
