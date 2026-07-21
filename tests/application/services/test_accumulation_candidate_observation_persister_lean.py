"""Negative-first tests for the lean-identity guardrails in
AccumulationCandidateObservationPersister (DQ-003 Slice A).

These prove the contract-rejection and fail-closed behavior without exercising
the full evidence-building path: the guards run before the persistence body.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.application.services.accumulation_candidate_observation_persister import (
    AccumulationCandidateObservationPersister,
)
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)

_VALID_ID = SemanticCompatibilityId("sha256:" + "b" * 64)


class _SpyRepo:
    def __init__(self) -> None:
        self.saved: list = []

    def save_many(self, observations) -> None:
        self.saved.extend(observations)


def _persister(repo) -> AccumulationCandidateObservationPersister:
    # The guards under test run before any collaborator is used, so None
    # collaborators are safe here.
    return AccumulationCandidateObservationPersister(
        candidate_observations_repository=repo,
        candidate_evidence_builder=None,  # type: ignore[arg-type]
        setup_family_resolver=None,  # type: ignore[arg-type]
        swing_setup_catalog=None,
    )


def test_persist_rejects_non_accumulation_discovery_contract() -> None:
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="observation_contract"):
        persister.persist(
            [object()],  # sentinel candidate — never inspected before the raise
            date(2026, 7, 16),
            object(),  # sentinel request
            observation_contract="named-swing-setup",
            semantic_compatibility_id=_VALID_ID,
        )


def test_persist_rejects_none_contract() -> None:
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="observation_contract"):
        persister.persist(
            [object()],
            date(2026, 7, 16),
            object(),
            observation_contract=None,
            semantic_compatibility_id=_VALID_ID,
        )


def test_canonical_write_with_none_compat_id_fails_closed() -> None:
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="semantic_compatibility_id"):
        persister.persist(
            [object()],  # truthy candidates → this IS a canonical write
            date(2026, 7, 16),
            object(),
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            semantic_compatibility_id=None,
        )


def test_none_repo_returns_zero_without_raising_on_none_compat_id() -> None:
    """Read-only path: no repository means no canonical write, so a None
    compatibility id must NOT raise — it returns 0."""
    persister = _persister(None)
    result = persister.persist(
        [object()],
        date(2026, 7, 16),
        object(),
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=None,
    )
    assert result == 0


def test_empty_candidates_returns_zero_without_raising_on_none_compat_id() -> None:
    """No candidates means no canonical write — a None id must not raise."""
    persister = _persister(_SpyRepo())
    result = persister.persist(
        [],
        date(2026, 7, 16),
        object(),
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=None,
    )
    assert result == 0


def test_bad_contract_raises_even_with_empty_candidates() -> None:
    """Contract rejection is unconditional — it precedes the no-op short-circuit."""
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="observation_contract"):
        persister.persist(
            [],
            date(2026, 7, 16),
            object(),
            observation_contract="named-swing-setup",
            semantic_compatibility_id=None,
        )
