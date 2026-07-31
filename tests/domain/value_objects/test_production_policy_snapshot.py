"""Contract tests for production_policy_snapshot.v1 (ADR-059)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
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


def _snapshot(
    *,
    policy_id: str = PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    payload: dict | None = None,
    created_at: datetime = NOW,
    source_revision: str = "rev-a",
    material: str = "sha256:" + ("ab" * 32),
) -> ProductionPolicySnapshot:
    return ProductionPolicySnapshot.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        learning_observation_contract_id=(LearningContractId.ACCUMULATION_OBSERVATION.value),
        producer_observation_contract="accumulation-discovery.v2",
        compatibility_id="sha256:" + ("cd" * 32),
        policy_id=policy_id,
        policy_version="v1",
        decision_type="score",
        semantic_engine_contract_id="accum_score_policy.v1",
        material_config_hash=material,
        canonical_payload=payload
        or {
            "policy_id": policy_id,
            "components": [{"key": "consistency", "weight": 33.3, "enabled": True}],
        },
        source_revision=source_revision,
        created_at=created_at,
    )


def test_snapshot_id_is_deterministic_and_excludes_provenance() -> None:
    later = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)
    a = _snapshot(created_at=NOW, source_revision="a")
    b = _snapshot(created_at=later, source_revision="b")
    assert a.snapshot_id == b.snapshot_id
    assert a.payload_digest == b.payload_digest


def test_snapshot_id_matches_stable_learning_id_formula() -> None:
    snap = _snapshot()
    expected = stable_learning_id(
        LearningContractId.PRODUCTION_POLICY_SNAPSHOT,
        {
            "purpose": AssessmentPurpose.ACCUMULATION_DISCOVERY,
            "learning_observation_contract_id": (LearningContractId.ACCUMULATION_OBSERVATION.value),
            "producer_observation_contract": "accumulation-discovery.v2",
            "compatibility_id": snap.compatibility_id,
            "policy_id": snap.policy_id,
        },
    )
    assert snap.snapshot_id == expected


def test_payload_digest_is_sha256_of_canonical_json_bytes() -> None:
    payload = {"policy_id": "x", "weight": 1.0, "nested": {"a": None, "b": True}}
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
    a = _snapshot(payload={"policy_id": "x", "w": 1.0})
    b = _snapshot(payload={"policy_id": "x", "w": 2.0})
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


def test_closed_v1_policy_id_set_has_exactly_six() -> None:
    assert len(ACCUMULATION_PRODUCTION_POLICY_IDS) == 6
    assert len(set(ACCUMULATION_PRODUCTION_POLICY_IDS)) == 6


def test_contract_id_enum_value() -> None:
    assert LearningContractId.PRODUCTION_POLICY_SNAPSHOT.value == "production_policy_snapshot.v1"
