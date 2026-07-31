"""Contract tests for production_policy_snapshot v1/v2 (ADR-059)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    ACCUMULATION_PRODUCTION_POLICY_IDS_V1,
    ACCUMULATION_PRODUCTION_POLICY_IDS_V2,
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
    AssessmentPurpose,
    LearningContractError,
    LearningContractId,
    ProductionPolicySnapshot,
    canonical_json,
    material_config_hash_from_canonical,
    policy_snapshot_payload_digest,
    stable_learning_id,
    validate_policy_snapshot_integrity,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)


def _default_payload(policy_id: str) -> dict:
    return {
        "policy_id": policy_id,
        "policy_version": "v1",
        "decision_type": "score",
        "semantic_engine_contract_id": "accum_score_policy.v1",
        "components": [{"key": "consistency", "weight": 33.3, "enabled": True}],
    }


def _snapshot(
    *,
    contract_id: LearningContractId = LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1,
    policy_id: str = PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    payload: dict | None = None,
    created_at: datetime = NOW,
    source_revision: str = "ai-saham@test+git:abc1234",
    material: str = "sha256:" + ("ab" * 32),
) -> ProductionPolicySnapshot:
    return ProductionPolicySnapshot.create(
        contract_id=contract_id,
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
        producer_observation_contract="accumulation-discovery.v2",
        compatibility_id="sha256:" + ("cd" * 32),
        policy_id=policy_id,
        policy_version="v1",
        decision_type="score",
        semantic_engine_contract_id="accum_score_policy.v1",
        material_config_hash=material,
        canonical_payload=payload or _default_payload(policy_id),
        source_revision=source_revision,
        created_at=created_at,
    )


def test_snapshot_id_is_deterministic_and_excludes_provenance() -> None:
    later = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
    a = _snapshot(created_at=NOW, source_revision="ai-saham@a")
    b = _snapshot(created_at=later, source_revision="ai-saham@b")
    assert a.snapshot_id == b.snapshot_id
    assert a.payload_digest == b.payload_digest


def test_snapshot_id_matches_stable_learning_id_formula_for_v1() -> None:
    snap = _snapshot(contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1)
    expected = stable_learning_id(
        LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1,
        {
            "purpose": AssessmentPurpose.ACCUMULATION_DISCOVERY,
            "learning_observation_contract_id": LearningContractId.ACCUMULATION_OBSERVATION.value,
            "producer_observation_contract": "accumulation-discovery.v2",
            "compatibility_id": snap.compatibility_id,
            "policy_id": snap.policy_id,
        },
    )
    assert snap.snapshot_id == expected


def test_v1_and_v2_snapshot_ids_differ_for_same_policy_identity() -> None:
    v1 = _snapshot(contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1)
    v2 = _snapshot(contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2)
    assert v1.snapshot_id != v2.snapshot_id
    assert v1.contract_id is LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1
    assert v2.contract_id is LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2


def test_payload_digest_is_sha256_of_canonical_json_bytes() -> None:
    payload = {
        **_default_payload(PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS),
        "weight": 1.0,
        "nested": {"a": None, "b": True},
    }
    snap = _snapshot(payload=payload)
    assert snap.payload_digest == policy_snapshot_payload_digest(payload)
    assert (
        snap.payload_digest
        == __import__("hashlib").sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    )
    assert ":" not in snap.payload_digest
    assert len(snap.payload_digest) == 64


def test_material_config_hash_prefixes_sha256() -> None:
    assert material_config_hash_from_canonical("cfg-bytes") == (
        "sha256:" + __import__("hashlib").sha256(b"cfg-bytes").hexdigest()
    )


def test_payload_change_changes_digest_not_id_when_identity_same() -> None:
    base = _default_payload(PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS)
    a = _snapshot(payload={**base, "w": 1.0})
    b = _snapshot(payload={**base, "w": 2.0})
    assert a.snapshot_id == b.snapshot_id
    assert a.payload_digest != b.payload_digest


def test_integrity_rejects_tampered_digest() -> None:
    snap = _snapshot()
    bad = ProductionPolicySnapshot(
        **{
            **snap.__dict__,
            "payload_digest": "0" * 64,
        }
    )
    with pytest.raises(LearningContractError, match="payload_digest"):
        validate_policy_snapshot_integrity(bad)


def test_create_rejects_empty_source_revision() -> None:
    with pytest.raises(LearningContractError, match="source_revision"):
        ProductionPolicySnapshot.create(
            contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
            producer_observation_contract="accumulation-discovery.v2",
            compatibility_id="sha256:" + ("cd" * 32),
            policy_id=PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
            policy_version="v1",
            decision_type="score",
            semantic_engine_contract_id="accum_score_policy.v1",
            material_config_hash="sha256:" + ("ab" * 32),
            canonical_payload=_default_payload(PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS),
            source_revision="",
            created_at=NOW,
        )


def test_create_requires_explicit_contract_id() -> None:
    with pytest.raises(TypeError):
        ProductionPolicySnapshot.create(  # type: ignore[call-arg]
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
            producer_observation_contract="accumulation-discovery.v2",
            compatibility_id="sha256:" + ("cd" * 32),
            policy_id=PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
            policy_version="v1",
            decision_type="score",
            semantic_engine_contract_id="accum_score_policy.v1",
            material_config_hash="sha256:" + ("ab" * 32),
            canonical_payload=_default_payload(PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS),
            source_revision="ai-saham@test",
            created_at=NOW,
        )


def test_create_rejects_payload_column_metadata_mismatch() -> None:
    with pytest.raises(LearningContractError, match="does not match column"):
        ProductionPolicySnapshot.create(
            contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1,
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            learning_observation_contract_id=LearningContractId.ACCUMULATION_OBSERVATION.value,
            producer_observation_contract="accumulation-discovery.v2",
            compatibility_id="sha256:" + ("cd" * 32),
            policy_id=PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
            policy_version="v1",
            decision_type="score",
            semantic_engine_contract_id="accum_score_policy.v1",
            material_config_hash="sha256:" + ("ab" * 32),
            canonical_payload={
                **_default_payload(PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS),
                "semantic_engine_contract_id": "other.contract",
            },
            source_revision="ai-saham@test",
            created_at=NOW,
        )


def test_integrity_rejects_payload_column_metadata_mismatch() -> None:
    snap = _snapshot(payload=_default_payload(PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS))
    mutated = {
        **dict(snap.canonical_payload),
        "decision_type": "gate",
    }
    bad = ProductionPolicySnapshot(
        **{
            **snap.__dict__,
            "canonical_payload": mutated,
            "payload_digest": policy_snapshot_payload_digest(mutated),
        }
    )
    with pytest.raises(LearningContractError, match="does not match column"):
        validate_policy_snapshot_integrity(bad)


def test_closed_v1_policy_id_set_has_exactly_six() -> None:
    assert len(ACCUMULATION_PRODUCTION_POLICY_IDS_V1) == 6
    assert len(set(ACCUMULATION_PRODUCTION_POLICY_IDS_V1)) == 6
    assert PRODUCTION_POLICY_ID_HARD_FILTERS not in ACCUMULATION_PRODUCTION_POLICY_IDS_V1


def test_closed_v2_policy_id_set_has_exactly_seven() -> None:
    assert len(ACCUMULATION_PRODUCTION_POLICY_IDS_V2) == 7
    assert len(set(ACCUMULATION_PRODUCTION_POLICY_IDS_V2)) == 7
    assert PRODUCTION_POLICY_ID_HARD_FILTERS in ACCUMULATION_PRODUCTION_POLICY_IDS_V2
    assert ACCUMULATION_PRODUCTION_POLICY_IDS is ACCUMULATION_PRODUCTION_POLICY_IDS_V2


def test_contract_id_enum_values() -> None:
    assert LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1.value == "production_policy_snapshot.v1"
    assert LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2.value == "production_policy_snapshot.v2"
