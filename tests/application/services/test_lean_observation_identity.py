"""Focused tests for the lean observation identity resolver and value object.

DQ-003 Slice A + ADR-059 v2: lean_accumulation_compatibility.v2 canonical-JSON
framing produces a stable semantic_compatibility_id; binding/config forks it.
"""

from __future__ import annotations

import hashlib
import re

import pytest

from src.application.services.lean_observation_identity import (
    LEAN_ACCUMULATION_COMPATIBILITY_CONTRACT_ID,
    POLICY_SNAPSHOT_BINDING_CONTRACT_V2,
    LeanObservationIdentity,
    resolve_lean_semantic_compatibility_id,
)
from src.domain.value_objects.learning_artifacts import canonical_json
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
    EVIDENCE_CONTRACT_VERSION,
    SEMANTIC_ENGINE_VERSION,
)

_SHA256_PREFIXED = re.compile(r"^sha256:[0-9a-f]{64}\Z")

# Locked golden vector (activation task §5.4; ADR-062 schema-12 fork).
_GOLDEN_CONFIG = "x: 1\n"
# Schema-12 retires Accum group-breadth material (ADR-062).
# schema-11 was sha256:e3546ed4…; schema-10 was sha256:12dc594c…;
# schema-9 was sha256:5b2849a0…).
_GOLDEN_COMPATIBILITY_ID = "sha256:19488deb57c0240f3e9e580a4dd50bb0dbaa9baba70e91c22e265589f50d9fb2"


def test_resolver_returns_valid_prefixed_sha256() -> None:
    result = resolve_lean_semantic_compatibility_id("some: config\nvalue: 1\n")
    assert isinstance(result, SemanticCompatibilityId)
    assert _SHA256_PREFIXED.match(result.value)


def test_same_config_resolves_to_identical_id() -> None:
    config = "accumulation_screener:\n  min_signal_score: 40\n"
    first = resolve_lean_semantic_compatibility_id(config)
    second = resolve_lean_semantic_compatibility_id(config)
    assert first == second
    assert first.value == second.value


def test_changed_config_value_forks_the_id() -> None:
    base = "accumulation_screener:\n  min_signal_score: 40\n"
    changed = "accumulation_screener:\n  min_signal_score: 41\n"
    assert resolve_lean_semantic_compatibility_id(base) != resolve_lean_semantic_compatibility_id(
        changed
    )


def test_lean_v2_golden_vector() -> None:
    """Exact frozen bytes and digest from the activation-task lock."""
    expected_material = (
        '{"candidate_observation_schema_version":12,'
        '"contract_id":"lean_accumulation_compatibility.v2",'
        '"evidence_contract_version":"1.5",'
        '"policy_snapshot_binding_contract":"production_policy_snapshot.v2",'
        '"resolved_config_canonical":"x: 1\\n",'
        '"semantic_engine_version":"1.5"}'
    )
    material = canonical_json(
        {
            "contract_id": LEAN_ACCUMULATION_COMPATIBILITY_CONTRACT_ID,
            "resolved_config_canonical": _GOLDEN_CONFIG,
            "candidate_observation_schema_version": CANDIDATE_OBSERVATION_SCHEMA_VERSION,
            "semantic_engine_version": SEMANTIC_ENGINE_VERSION,
            "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
            "policy_snapshot_binding_contract": POLICY_SNAPSHOT_BINDING_CONTRACT_V2,
        }
    )
    assert material == expected_material
    assert CANDIDATE_OBSERVATION_SCHEMA_VERSION == 12
    assert SEMANTIC_ENGINE_VERSION == "1.5"
    assert EVIDENCE_CONTRACT_VERSION == "1.5"
    assert resolve_lean_semantic_compatibility_id(_GOLDEN_CONFIG).value == _GOLDEN_COMPATIBILITY_ID
    assert (
        "sha256:" + hashlib.sha256(expected_material.encode("utf-8")).hexdigest()
        == _GOLDEN_COMPATIBILITY_ID
    )


def test_delimiter_free_v1_algorithm_is_not_an_alias() -> None:
    """Old concat hash must not equal lean.v2 (no dual-path acceptance)."""
    config = _GOLDEN_CONFIG
    legacy = (
        "sha256:"
        + hashlib.sha256(
            (
                config
                + str(CANDIDATE_OBSERVATION_SCHEMA_VERSION)
                + SEMANTIC_ENGINE_VERSION
                + EVIDENCE_CONTRACT_VERSION
            ).encode("utf-8")
        ).hexdigest()
    )
    current = resolve_lean_semantic_compatibility_id(config).value
    assert current != legacy
    assert current == _GOLDEN_COMPATIBILITY_ID


def test_resolver_rejects_non_string() -> None:
    with pytest.raises(ValueError):
        resolve_lean_semantic_compatibility_id(123)  # type: ignore[arg-type]


def test_lean_identity_holds_contract_and_compat_id() -> None:
    compat = resolve_lean_semantic_compatibility_id("x: 1\n")
    identity = LeanObservationIdentity(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=compat,
    )
    assert identity.observation_contract == ACCUMULATION_DISCOVERY_CONTRACT
    assert identity.semantic_compatibility_id is compat


def test_lean_identity_rejects_blank_contract() -> None:
    compat = resolve_lean_semantic_compatibility_id("x: 1\n")
    with pytest.raises(ValueError):
        LeanObservationIdentity(
            observation_contract="  ",
            semantic_compatibility_id=compat,
        )


def test_lean_identity_rejects_non_compat_id_type() -> None:
    with pytest.raises(ValueError):
        LeanObservationIdentity(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            semantic_compatibility_id="sha256:" + "0" * 64,  # type: ignore[arg-type]
        )


def test_semantic_engine_version_participates_in_fork(monkeypatch: pytest.MonkeyPatch) -> None:
    """A SEMANTIC_ENGINE_VERSION bump must fork the cohort id even though the
    config content passed to the resolver is byte-for-byte identical."""
    config = "accumulation_screener:\n  min_signal_score: 40\n"
    unpatched = resolve_lean_semantic_compatibility_id(config)

    monkeypatch.setattr(
        "src.application.services.lean_observation_identity.SEMANTIC_ENGINE_VERSION",
        "9.9-test",
    )
    patched = resolve_lean_semantic_compatibility_id(config)

    assert patched != unpatched
    assert patched.value != unpatched.value


def test_binding_contract_participates_in_fork(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _GOLDEN_CONFIG
    base = resolve_lean_semantic_compatibility_id(config)
    monkeypatch.setattr(
        "src.application.services.lean_observation_identity.POLICY_SNAPSHOT_BINDING_CONTRACT_V2",
        "production_policy_snapshot.v1",
    )
    forked = resolve_lean_semantic_compatibility_id(config)
    assert forked != base
