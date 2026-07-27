"""Focused tests for the lean observation identity resolver and value object.

DQ-003 Slice A: a whole-config-content hash produces a stable
`semantic_compatibility_id` cohort tag; any config change forks it.
"""

from __future__ import annotations

import re

import pytest

from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
    resolve_lean_semantic_compatibility_id,
)
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


def test_id_folds_in_contract_versions() -> None:
    """The hash must incorporate the schema/engine/evidence versions, so a
    version bump forks the cohort even with identical config content."""
    import hashlib

    config = "x: 1\n"
    expected = (
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
    assert resolve_lean_semantic_compatibility_id(config).value == expected


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
