"""Negative-first tests for ADR-056 multi-window session persist guards.

Guards run before the evidence-building body.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from src.application.services.accumulation_candidate_observation_persister import (
    AccumulationCandidateObservationPersister,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
    stable_learning_id,
    stamp_universe_membership_id,
)
from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
)
from src.domain.value_objects.signal_semantic_contract import (
    ACCUMULATION_DISCOVERY_CONTRACT,
)
from tests.fixtures.diagnostic_producer_identity import (
    valid_accumulation_diagnostic_bindings,
)

_VALID_ID = SemanticCompatibilityId("sha256:" + "b" * 64)


class _SpyRepo:
    def __init__(self) -> None:
        self.saved: list = []
        self.existing_ids: set[str] = set()
        self.get_calls: list[str] = []

    def add_observation(self, observation) -> bool:
        self.saved.append(observation)
        return True

    def get_observation(self, observation_id: str):
        self.get_calls.append(observation_id)
        if observation_id in self.existing_ids:
            return object()
        return None


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


def _test_population_binding(session: date = date(2026, 7, 16), tickers=None):
    from src.domain.value_objects.learning_artifacts import AccumPopulationBinding

    tickers = tickers or ["BBCA"]
    return AccumPopulationBinding.create(
        membership_tickers=tickers,
        named_universe_tickers=["ASII", "BBCA", "BBRI"],
        membership_session=session,
        pit_tradable_lookback_sessions=10,
        producer_source_revision="ai-saham@test+git:deadbeef",
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
        population_binding=_test_population_binding(),
        diagnostic_bindings=valid_accumulation_diagnostic_bindings(),
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
            population_binding=_test_population_binding(),
            diagnostic_bindings=valid_accumulation_diagnostic_bindings(),
        )


def test_persist_skips_existing_observation_without_rebuild() -> None:
    """Re-backfill must skip existing observation_id (no digest conflict).

    ADR-068 removed the ``compute_accumulation_config_hash`` stub this test used
    to pin: the persister no longer computes a config hash at all, so there is
    nothing left to hold still.
    """
    repo = _SpyRepo()
    session = _session()
    session.decision_at = datetime(2026, 7, 16, 16, 0, tzinfo=IDX_TIMEZONE)
    universe = ["BBCA"]
    universe_id = stamp_universe_membership_id(universe)
    window_id = "BBCA:2026-07-16"
    obs_id = stable_learning_id(
        LearningContractId.ACCUMULATION_OBSERVATION,
        {
            "purpose": AssessmentPurpose.ACCUMULATION_DISCOVERY,
            "policy_contract": "accumulation_discovery.policy.v1",
            "horizon_contract": "accum_10d",
            "compatibility_id": str(_VALID_ID),
            "cutoff_at": session.decision_at,
            "universe_id": universe_id,
            "window_id": window_id,
        },
    )
    repo.existing_ids.add(obs_id)
    oc = SimpleNamespace(
        candidate=SimpleNamespace(ticker="BBCA", current_price=1000),
        screen_result="WATCH",
        flow_evidence=None,
    )
    req = SimpleNamespace(market_context=None, window_days=7)
    saved = _persister(repo).persist_session_multi_window(
        window_results={
            7: (req, [oc]),
            30: (req, [oc]),
            90: (req, [oc]),
        },
        snapshot_date=date(2026, 7, 16),
        effective_session=session,
        observation_contract=ACCUMULATION_DISCOVERY_CONTRACT,
        semantic_compatibility_id=_VALID_ID,
        universe_tickers=universe,
        population_binding=_test_population_binding(tickers=universe),
        diagnostic_bindings=valid_accumulation_diagnostic_bindings(),
    )
    assert saved == 0
    assert repo.saved == []
    assert obs_id in repo.get_calls


def test_persist_rejects_tampered_count_and_named_digest_before_insert() -> None:
    """Inconsistent count/named-digest dict must not insert schema-10 rows."""
    from dataclasses import replace

    from src.domain.value_objects.learning_artifacts import stamp_universe_membership_id

    repo = _SpyRepo()
    persister = _persister(repo)
    base = _test_population_binding(tickers=["BBCA"])
    invented = stamp_universe_membership_id(["FAKE1", "FAKE2"])
    adversarial = replace(base, membership_count=999, named_universe_digest=invented)
    with pytest.raises(ValueError, match="population_binding rejected before persist"):
        _call(persister, population_binding=adversarial, universe_tickers=["BBCA"])
    assert repo.saved == []
    assert repo.get_calls == []

    # Dict injection path (bypass typed object field defaults) also fails closed.
    adversarial_dict = adversarial.to_dict()
    with pytest.raises(ValueError, match="population_binding rejected before persist"):
        _call(persister, population_binding=adversarial_dict, universe_tickers=["BBCA"])
    assert repo.saved == []


def test_persist_rejects_unsupported_population_name_before_insert() -> None:
    """idx30 (or any non-lq45) binding must not write schema-10 observations.

    Adversarial path: inject via replace after create would reject, simulating
    a bypass of AccumPopulationBinding.create.
    """
    from dataclasses import replace

    from src.domain.value_objects.learning_artifacts import ACCUM_POPULATION_NAME

    repo = _SpyRepo()
    persister = _persister(repo)
    base = _test_population_binding(tickers=["BBCA"])
    assert base.population_name == ACCUM_POPULATION_NAME
    adversarial = replace(base, population_name="idx30")
    assert adversarial.population_name == "idx30"
    with pytest.raises(ValueError, match="population_binding rejected before persist"):
        _call(persister, population_binding=adversarial, universe_tickers=["BBCA"])
    assert repo.saved == []
    assert repo.get_calls == []

    # lq45 binding clears the population gate; incomplete OC mocks fail later
    # without writing rows and without a population_name rejection.
    with pytest.raises(AttributeError):
        _call(persister, population_binding=base, universe_tickers=["BBCA"])
    assert repo.saved == []
