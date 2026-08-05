"""Focused tests for the lean observation identity value object.

ADR-068 removed this module's resolver. ``lean_observation_identity`` used to
own ``resolve_lean_semantic_compatibility_id`` — a hash over raw config bytes
folded with two hand-typed engine version constants. All three were identity
*proxies* and all three were wrong (ADR-068 §"Context"), so they were deleted
with no alias and no fallback. The cohort tag is now measured behaviour, resolved
by ``behavioral_cohort_identity`` and tested in
``test_behavioral_cohort_identity.py``.

What is left here is the narrow value object that carries the resulting
``(observation_contract, semantic_compatibility_id)`` pair to the writers, plus a
structural guard that the deleted formula has not crept back.
"""

from __future__ import annotations

import pytest

from src.application.services import lean_observation_identity as module
from src.application.services.lean_observation_identity import (
    POLICY_SNAPSHOT_BINDING_CONTRACT_V2,
    LeanObservationIdentity,
)
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)

_COMPAT = SemanticCompatibilityId("sha256:" + "ab" * 32)


def test_lean_identity_holds_contract_and_compat_id() -> None:
    identity = LeanObservationIdentity(
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=_COMPAT,
    )
    assert identity.observation_contract == ACCUMULATION_DISCOVERY_CONTRACT
    assert identity.semantic_compatibility_id is _COMPAT


def test_lean_identity_rejects_blank_contract() -> None:
    with pytest.raises(ValueError):
        LeanObservationIdentity(
            observation_contract="  ",
            semantic_compatibility_id=_COMPAT,
        )


def test_lean_identity_rejects_non_compat_id_type() -> None:
    with pytest.raises(ValueError):
        LeanObservationIdentity(
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            semantic_compatibility_id="sha256:" + "0" * 64,  # type: ignore[arg-type]
        )


def test_policy_snapshot_binding_contract_survives_adr_068() -> None:
    """ADR-068 §8: the binding contract is explicitly *not* deleted.

    It names which closed snapshot set a cohort is bound to and is consumed by
    accumulation readiness, not by identity resolution. Pinned so the ADR-068
    deletions cannot take it along by association.
    """
    assert POLICY_SNAPSHOT_BINDING_CONTRACT_V2 == "production_policy_snapshot.v2"


def test_config_byte_identity_formula_is_gone_with_no_alias() -> None:
    """ADR-068 §7 / task §4: clean break, no dual-identity path.

    Asserted on the module object rather than by grep so a re-added private
    helper or a re-export is caught too.
    """
    for deleted in (
        "resolve_lean_semantic_compatibility_id",
        "LEAN_ACCUMULATION_COMPATIBILITY_CONTRACT_ID",
    ):
        assert not hasattr(module, deleted), (
            f"{deleted} was deleted by ADR-068; identity must have exactly one "
            "mechanism and no 'just in case' fallback"
        )

    source = module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "hashlib" not in text, "the lean identity module must no longer hash anything"
