"""Negative-first tests for ADR-056 multi-window session persist guards.

Guards run before the evidence-building body.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

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

    def add_observation(self, observation) -> bool:
        self.saved.append(observation)
        return True


def _persister(repo) -> AccumulationCandidateObservationPersister:
    return AccumulationCandidateObservationPersister(
        candidate_observations_repository=repo,
        candidate_evidence_builder=None,  # type: ignore[arg-type]
        setup_family_resolver=None,  # type: ignore[arg-type]
        swing_setup_catalog=None,
    )


def _session():
    return SimpleNamespace(
        decision_at=None,
        latest_completed_session=date(2026, 7, 16),
        analysis_as_of=date(2026, 7, 16),
        market_session_name="REGULAR",
        is_eod_pending=False,
        resolution_source="test",
        notes=(),
    )


def _call(persister, **kwargs):
    base = dict(
        window_results={
            7: (object(), [object()]),
            30: (object(), [object()]),
            90: (object(), [object()]),
        },
        snapshot_date=date(2026, 7, 16),
        effective_session=_session(),
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=_VALID_ID,
        universe_tickers=["BBCA"],
    )
    base.update(kwargs)
    return persister.persist_session_multi_window(**base)


def test_persist_rejects_non_accumulation_discovery_contract() -> None:
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="observation_contract"):
        _call(persister, observation_contract="named-swing-setup")


def test_persist_rejects_removed_unversioned_contract() -> None:
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="observation_contract"):
        _call(persister, observation_contract="accumulation-discovery")


def test_persist_rejects_none_contract() -> None:
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="observation_contract"):
        _call(persister, observation_contract=None)


def test_canonical_write_with_none_compat_id_fails_closed() -> None:
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="semantic_compatibility_id"):
        _call(persister, semantic_compatibility_id=None)


def test_none_repo_returns_zero_without_raising_on_none_compat_id() -> None:
    persister = _persister(None)
    result = _call(persister, semantic_compatibility_id=None)
    assert result == 0


def test_missing_required_window_raises() -> None:
    persister = _persister(_SpyRepo())
    with pytest.raises(ValueError, match="missing required window"):
        persister.persist_session_multi_window(
            window_results={7: (object(), []), 30: (object(), [])},
            snapshot_date=date(2026, 7, 16),
            effective_session=_session(),
            observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
            semantic_compatibility_id=_VALID_ID,
            universe_tickers=["BBCA"],
        )
