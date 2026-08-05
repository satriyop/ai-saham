"""Frozen digest-contract fixtures for database-owned learning artifacts.

These tests pin the *exact* identity and digest bytes produced by
``learning_artifacts``. They exist because a relative assertion (two artifacts
hash the same as each other) stays green when the hashing rule itself changes,
which is how a digest-material change once silently invalidated every stored
label without failing CI.

If a test in this module fails, the hashing contract changed. That is a
``LABEL_SCHEMA`` / ``OBSERVATION_SCHEMA`` class change, not a test bug. Do not
refresh the constants to make it pass. Instead:

1. Confirm the change to digest material is intended.
2. Bump ``LEARNING_SCHEMA_VERSION`` so old and new rows are distinguishable.
3. Update these fixtures in the same commit, keeping the old values recorded in
   the commit message.

Stored rows written under an earlier version stay byte-for-byte unchanged; they
are never rewritten to look as though the new contract produced them.
"""

from dataclasses import fields, replace
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
    LearningPolicyApplication,
    LearningPolicyProposal,
    LearningPolicyValidation,
    LearningTrackSnapshot,
    OutcomeBasis,
    ValidationStatus,
    _artifact_payload,
    canonical_json,
    validate_artifact_integrity,
)

FROZEN_AT = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)
LATER = datetime(2026, 7, 28, 9, 36, tzinfo=timezone.utc)


def _observation() -> LearningObservation:
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation.policy.v1",
        horizon_contract="accum_10d",
        compatibility_id="compat-1",
        cutoff_at=FROZEN_AT,
        universe_id="idx30",
        window_id="BBCA:2026-07-27",
        decision_payload={"funnel": "PASS", "score": 72.0},
        captured_at=FROZEN_AT,
        producer_source_revision="ai-saham@test",
    )


def _track() -> LearningTrackSnapshot:
    return LearningTrackSnapshot.create(
        observation_id=_observation().observation_id,
        sampled_at=FROZEN_AT,
        source="stockbit.opening_track",
        snapshot_payload={"last_price": 9500, "volume": 1200},
        captured_at=FROZEN_AT,
    )


def _label(*, labeled_at: datetime = FROZEN_AT) -> LearningOutcomeLabel:
    return LearningOutcomeLabel.create(
        contract_id=LearningContractId.ACCUM_10D_LABEL,
        observation_id=_observation().observation_id,
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        availability=LabelAvailability.AVAILABLE,
        outcome="SUCCESS",
        metrics={"forward_return_pct": 3.25},
        fingerprint="tracks-1",
        labeled_at=labeled_at,
    )


def _evaluation() -> LearningEvaluation:
    return LearningEvaluation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        method=EvaluationMethod.FORWARD_OUTCOME_COHORT,
        compatibility_id="compat-1",
        dataset_fingerprint="dataset-1",
        split_contract="chronological.v1",
        population={"observation_ids": [_observation().observation_id]},
        exclusions={},
        metrics={"average_return": 1.2},
        outcome_basis=OutcomeBasis.PRICE_PATH_ONLY,
        readiness=EvaluationReadiness.OOS_DIAGNOSTIC_READY,
        evaluated_at=FROZEN_AT,
    )


def _proposal() -> LearningPolicyProposal:
    return LearningPolicyProposal.create(
        source_evaluation_id=_evaluation().evaluation_id,
        current_config_hash="config-hash-before",
        changes={"config/swing_backtest.yaml:take_profit_pct": 6.0},
        rationale={"reason": "profit factor above one"},
        created_at=FROZEN_AT,
    )


def _validation() -> LearningPolicyValidation:
    return LearningPolicyValidation.create(
        proposal_id=_proposal().proposal_id,
        baseline_evaluation_id=_evaluation().evaluation_id,
        proposed_evaluation_id=_evaluation().evaluation_id,
        population_fingerprint="population-1",
        paired_deltas={
            "net_return": 0.4,
            "profit_factor": 0.2,
            "average_return": 0.1,
            "drawdown_regression": 0.0,
            "trade_count": 0,
            "regime_stability": 0.0,
            "authority_coverage": 1.0,
            "setup_readiness": 1.0,
        },
        issues=(),
        status=ValidationStatus.PASS,
        validated_at=FROZEN_AT,
    )


def _application() -> LearningPolicyApplication:
    return LearningPolicyApplication.create(
        proposal_id=_proposal().proposal_id,
        validation_id=_validation().validation_id,
        previous_config_hash="config-hash-before",
        applied_config_hash="config-hash-after",
        exact_changes={"config/swing_backtest.yaml:take_profit_pct": 6.0},
        confirmation_identity="operator-1",
        applied_at=FROZEN_AT,
        reread_verified=True,
    )


# name -> (builder, id field, frozen id, frozen digest)
FROZEN_CONTRACT = {
    "observation": (
        _observation,
        "observation_id",
        "75177cf6ecf64c9e0887704a8466498719541b013bae524305e4a6c71ec31fa4",
        "3b91743f5a9e322d0cf47bfa1bdd8537e77b9fdf64b08537239110fdfabfa47a",
    ),
    "track": (
        _track,
        "snapshot_id",
        "dc01b8a40b0b741a65c654d88ecca93b24066196c7b43c1743fc18787996554d",
        "6eca7604b5767f92811a3b86078fc2603730f731ea244b9f564a6102c90e012c",
    ),
    "label": (
        _label,
        "label_id",
        "dbc13e22138468777bbf97aeaf56cefbaf072c75ac4c78eb01e5b21a29f5979a",
        "27a742dfe4aaee3a6bc16770cb7e59b8bc6e8494754b99b207fc72fdf19c345a",
    ),
    "evaluation": (
        _evaluation,
        "evaluation_id",
        "0bb08a28adf31ff5e5173f4d718f6fee2d395a8d4211e0117cf447a447e2ece4",
        "0643553e0e819a4d991678d5ead8290d5f2937d4e7f7695a8925f356df41f3d1",
    ),
    "proposal": (
        _proposal,
        "proposal_id",
        "0a8403dc32146d5426d6c0f42a02842bd7d02791decf9da829741ba38e2cee1b",
        "2e9615307fe8eb3b9dd553dd6f844b5d519797fdf7346992d1ee7e9c8cf97853",
    ),
    "validation": (
        _validation,
        "validation_id",
        "e422b598a93d12a476f63278fb5e0407634c9eeff0b82566203e82382063cd77",
        "20fb0d5e40aa4faec7e717e978b427bf97d0f889e2b173ed38efc655dc822b69",
    ),
    "application": (
        _application,
        "application_id",
        "6d6f2dc366b112ac8a50f43262860aee0f5b20a1daa7a700a616c0415e7ee3ee",
        "e6b487ae19c6927012c5e7256bd85992533c73326c783b949c6aa56f3a328ef6",
    ),
}

# Exact fields that feed each digest. A new dataclass field lands here first,
# which names the culprit instead of only reporting a changed hash.
FROZEN_DIGEST_FIELDS = {
    "observation": (
        "schema_version",
        "contract_id",
        "purpose",
        "policy_contract",
        "horizon_contract",
        "compatibility_id",
        "cutoff_at",
        "universe_id",
        "window_id",
        "decision_payload",
        "captured_at",
    ),
    "track": (
        "schema_version",
        "observation_id",
        "sampled_at",
        "source",
        "snapshot_payload",
        "captured_at",
    ),
    "label": (
        "schema_version",
        "contract_id",
        "observation_id",
        "outcome_basis",
        "availability",
        "outcome",
        "metrics",
        "fingerprint",
    ),
    "evaluation": (
        "schema_version",
        "contract_id",
        "purpose",
        "method",
        "compatibility_id",
        "dataset_fingerprint",
        "split_contract",
        "population",
        "exclusions",
        "metrics",
        "outcome_basis",
        "readiness",
        "evaluated_at",
    ),
    "proposal": (
        "schema_version",
        "contract_id",
        "source_evaluation_id",
        "current_config_hash",
        "changes",
        "rationale",
        "created_at",
    ),
    "validation": (
        "schema_version",
        "contract_id",
        "proposal_id",
        "baseline_evaluation_id",
        "proposed_evaluation_id",
        "population_fingerprint",
        "paired_deltas",
        "issues",
        "status",
        "validated_at",
    ),
    "application": (
        "schema_version",
        "contract_id",
        "proposal_id",
        "validation_id",
        "previous_config_hash",
        "applied_config_hash",
        "exact_changes",
        "confirmation_identity",
        "applied_at",
        "reread_verified",
    ),
}

# Operational fields each artifact keeps out of its digest. Only the label has
# one: a cron re-run must not turn an unchanged outcome into a conflict.
FROZEN_DIGEST_EXCLUSIONS = {
    "observation": (LearningObservation, frozenset({"producer_source_revision"})),
    "track": (LearningTrackSnapshot, frozenset()),
    "label": (LearningOutcomeLabel, frozenset({"labeled_at"})),
    "evaluation": (LearningEvaluation, frozenset()),
    "proposal": (LearningPolicyProposal, frozenset()),
    "validation": (LearningPolicyValidation, frozenset()),
    "application": (LearningPolicyApplication, frozenset()),
}

ARTIFACT_NAMES = sorted(FROZEN_CONTRACT)


@pytest.mark.parametrize("name", ARTIFACT_NAMES)
def test_artifact_id_matches_frozen_contract(name: str) -> None:
    builder, id_field, frozen_id, _ = FROZEN_CONTRACT[name]

    assert getattr(builder(), id_field) == frozen_id


@pytest.mark.parametrize("name", ARTIFACT_NAMES)
def test_artifact_digest_matches_frozen_contract(name: str) -> None:
    builder, _, _, frozen_digest = FROZEN_CONTRACT[name]

    assert builder().artifact_digest == frozen_digest


@pytest.mark.parametrize("name", ARTIFACT_NAMES)
def test_digest_material_fields_match_frozen_contract(name: str) -> None:
    builder, id_field, _, _ = FROZEN_CONTRACT[name]
    payload = _artifact_payload(builder(), id_field=id_field, digest_field="artifact_digest")

    assert tuple(payload) == FROZEN_DIGEST_FIELDS[name]


@pytest.mark.parametrize("name", ARTIFACT_NAMES)
def test_declared_digest_exclusions_are_frozen(name: str) -> None:
    artifact_type, expected = FROZEN_DIGEST_EXCLUSIONS[name]

    assert artifact_type.DIGEST_EXCLUDED_FIELDS == expected


@pytest.mark.parametrize("name", ARTIFACT_NAMES)
def test_every_artifact_declares_its_exclusions(name: str) -> None:
    """A new artifact type must state its digest contract, not inherit a default."""
    artifact_type, _ = FROZEN_DIGEST_EXCLUSIONS[name]

    assert "DIGEST_EXCLUDED_FIELDS" in vars(artifact_type)


@pytest.mark.parametrize("name", ARTIFACT_NAMES)
def test_declared_exclusions_are_real_fields(name: str) -> None:
    """A stale exclusion name would silently widen the hash."""
    builder, _, _, _ = FROZEN_CONTRACT[name]
    artifact_type, _ = FROZEN_DIGEST_EXCLUSIONS[name]
    field_names = {field.name for field in fields(builder())}

    assert artifact_type.DIGEST_EXCLUDED_FIELDS <= field_names


def test_label_digest_material_omits_labeled_at() -> None:
    """Ops wall clock is audit-only; it must never reach the hash."""
    payload = _artifact_payload(_label(), id_field="label_id", digest_field="artifact_digest")

    assert "labeled_at" not in payload


def test_label_rerun_reproduces_the_frozen_digest() -> None:
    """A cron re-run at a different wall clock yields the same stored bytes."""
    _, _, frozen_id, frozen_digest = FROZEN_CONTRACT["label"]
    rerun = _label(labeled_at=LATER)

    assert rerun.labeled_at == LATER
    assert rerun.label_id == frozen_id
    assert rerun.artifact_digest == frozen_digest


@pytest.mark.parametrize("name", ARTIFACT_NAMES)
def test_schema_version_is_digest_material(name: str) -> None:
    """Bumping the version must change digests, so cohorts stay distinguishable."""
    assert "schema_version" in FROZEN_DIGEST_FIELDS[name]


def test_canonical_json_byte_layout_is_frozen() -> None:
    encoded = canonical_json(
        {
            "b": 1,
            "a": [2, 3],
            "c": {"z": None, "y": True},
            "s": "café",
            "t": FROZEN_AT,
        }
    )

    assert encoded == (
        '{"a":[2,3],"b":1,"c":{"y":true,"z":null},"s":"caf\\u00e9","t":"2026-07-27T01:00:00+00:00"}'
    )


def test_mutated_payload_fails_integrity_validation() -> None:
    tampered = replace(_label(), outcome="FAILURE")

    with pytest.raises(LearningContractError, match="does not match its payload"):
        validate_artifact_integrity(tampered, id_field="label_id")


def test_relabeling_at_a_new_wall_clock_still_validates() -> None:
    validate_artifact_integrity(_label(labeled_at=LATER), id_field="label_id")
