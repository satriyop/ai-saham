"""Tests for EnsureAccumulationPolicySnapshotsUseCase (ADR-059 v3 + ADR-068)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Sequence

import pytest

from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
)
from src.application.services.behavioral_cohort_identity import (
    resolve_accumulation_cohort_identity,
)
from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.ensure_accumulation_policy_snapshots_use_case import (
    EnsureAccumulationPolicySnapshotsRequest,
    EnsureAccumulationPolicySnapshotsUseCase,
)
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.rules.risk_gate import UnevaluableGateAction, UnevaluableGatePolicy
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
    PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY,
    AssessmentPurpose,
    LearningContractError,
    LearningContractId,
    ProductionPolicySnapshot,
)
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
)

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
SOURCE_REVISION = "ai-saham@test+git:deadbeef"


class _MemoryPolicySnapshotRepo:
    def __init__(self) -> None:
        self.rows: dict[str, ProductionPolicySnapshot] = {}
        self.batch_calls: list[tuple[str, ...]] = []

    def add_policy_snapshot(self, artifact: ProductionPolicySnapshot) -> bool:
        raise AssertionError("single-row add must not be used by ensure use case")

    def add_policy_snapshots_atomic(
        self, artifacts: Sequence[ProductionPolicySnapshot]
    ) -> tuple[int, int]:
        self.batch_calls.append(tuple(a.snapshot_id for a in artifacts))
        # Simulate all-or-nothing: apply to a staging map first.
        staging = dict(self.rows)
        inserted = 0
        reused = 0
        for artifact in artifacts:
            existing = staging.get(artifact.snapshot_id)
            if existing is not None:
                if existing.payload_digest == artifact.payload_digest:
                    reused += 1
                    continue
                raise LearningContractError(
                    "immutable artifact conflict for learning_policy_snapshots."
                    f"{artifact.snapshot_id}"
                )
            staging[artifact.snapshot_id] = artifact
            inserted += 1
        self.rows = staging
        return inserted, reused

    def get_policy_snapshot(self, snapshot_id: str) -> ProductionPolicySnapshot | None:
        return self.rows.get(snapshot_id)

    def get_policy_snapshot_by_binding(
        self,
        *,
        purpose: AssessmentPurpose,
        compatibility_id: str,
        policy_id: str,
    ) -> ProductionPolicySnapshot | None:
        for row in self.rows.values():
            if (
                row.purpose is purpose
                and row.compatibility_id == compatibility_id
                and row.policy_id == policy_id
            ):
                return row
        return None

    def list_policy_snapshots(
        self,
        *,
        purpose: AssessmentPurpose,
        compatibility_id: str,
    ) -> Sequence[ProductionPolicySnapshot]:
        return tuple(
            r
            for r in self.rows.values()
            if r.purpose is purpose and r.compatibility_id == compatibility_id
        )


def _default_hard_filters() -> AccumulationScreenHardFilterPolicy:
    return AccumulationScreenHardFilterPolicy(
        min_market_cap_idr=0,
        min_piotroski=0,
        min_accum_score=0.0,
        min_accum_score_enabled=True,
        min_signal_score=45.0,
        min_signal_score_enabled=False,
    )


def _request(
    *,
    accum: AccumScorePolicy | None = None,
    signal: SignalEngineConfig | None = None,
    hard_filter: AccumulationScreenHardFilterPolicy | None = None,
    unevaluable: UnevaluableGatePolicy | None = None,
    created_at: datetime = NOW,
    source_revision: str = SOURCE_REVISION,
) -> EnsureAccumulationPolicySnapshotsRequest:
    """Build a request whose stamped identity matches its own typed policies.

    This mirrors the production composition root: the adapter resolves the cohort
    id from the *same* typed policy objects it hands the use case, so the
    recompute inside ``execute`` agrees by construction. Tests that want a
    mismatch construct one explicitly.
    """
    accum_score_policy = accum or AccumScorePolicy()
    signal_engine_config = signal or SignalEngineConfig()
    structural_gates = [FundamentalGate(), LiquidityGate()]
    execution_gates = [BandarGate()]
    hard_filter_policy = hard_filter or _default_hard_filters()
    unevaluable_gate_policy = unevaluable or UnevaluableGatePolicy()
    identity = resolve_accumulation_cohort_identity(
        accum_score_policy=accum_score_policy,
        signal_engine_config=signal_engine_config,
        structural_gates=structural_gates,
        execution_gates=execution_gates,
        hard_filter_policy=hard_filter_policy,
        unevaluable_gate_policy=unevaluable_gate_policy,
    )
    return EnsureAccumulationPolicySnapshotsRequest(
        observation_identity=LeanObservationIdentity(
            observation_contract=ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
            semantic_compatibility_id=identity.semantic_compatibility_id,
        ),
        accum_score_policy=accum_score_policy,
        signal_engine_config=signal_engine_config,
        structural_gates=structural_gates,
        execution_gates=execution_gates,
        hard_filter_policy=hard_filter_policy,
        unevaluable_gate_policy=unevaluable_gate_policy,
        created_at=created_at,
        source_revision=source_revision,
    )


def test_ensure_writes_exactly_eight_closed_v3_policy_ids() -> None:
    repo = _MemoryPolicySnapshotRepo()
    response = EnsureAccumulationPolicySnapshotsUseCase(repo).execute(_request())

    assert response.inserted_count == 8
    assert response.reused_count == 0
    assert response.required_policy_ids == ACCUMULATION_PRODUCTION_POLICY_IDS
    assert len(repo.rows) == 8
    assert len(repo.batch_calls) == 1
    assert len(repo.batch_calls[0]) == 8
    written_ids = {r.policy_id for r in repo.rows.values()}
    assert written_ids == set(ACCUMULATION_PRODUCTION_POLICY_IDS)
    assert PRODUCTION_POLICY_ID_HARD_FILTERS in written_ids
    assert PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY in written_ids
    for snap in repo.rows.values():
        assert snap.source_revision == SOURCE_REVISION
        assert snap.contract_id is LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V3


def test_ensure_hard_filter_payload_is_pre_neutralization_policy() -> None:
    """Capture neutralization must not change the snapshot hard-filter row."""
    production = AccumulationScreenHardFilterPolicy(
        min_market_cap_idr=0,
        min_piotroski=0,
        min_accum_score=0.0,
        min_accum_score_enabled=True,
        min_signal_score=45.0,
        min_signal_score_enabled=False,
    )
    # Neutralized request would have enabled=False and floors 0 — not used here.
    repo = _MemoryPolicySnapshotRepo()
    EnsureAccumulationPolicySnapshotsUseCase(repo).execute(_request(hard_filter=production))
    hard = next(r for r in repo.rows.values() if r.policy_id == PRODUCTION_POLICY_ID_HARD_FILTERS)
    assert hard.canonical_payload["filters"]["accum_score"]["enabled"] is True
    assert hard.canonical_payload["filters"]["accum_score"]["floor"] == 0.0
    assert hard.canonical_payload["filters"]["signal_score"]["enabled"] is False
    assert hard.canonical_payload["filters"]["signal_score"]["floor"] == 45.0


def test_ensure_is_idempotent_for_same_cohort_content() -> None:
    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    first = use_case.execute(_request())
    second = use_case.execute(_request())

    assert first.inserted_count == 8
    assert second.inserted_count == 0
    assert second.reused_count == 8
    assert len(repo.rows) == 8
    assert len(repo.batch_calls) == 2


def test_ensure_rejects_compatibility_mismatch() -> None:
    """Fail-closed guard: a stamped id that does not match the policies written.

    This is the surviving half of the old double-read defence. ADR-068 removed
    the config-byte re-read because the guarantee became structural — identity is
    derived from the very payloads these rows serialize — but the recompute-and-
    compare stays, because the caller stamps the id on its observations
    separately and a wiring bug there must not reach the corpus.
    """
    repo = _MemoryPolicySnapshotRepo()
    request = _request()
    bad = EnsureAccumulationPolicySnapshotsRequest(
        observation_identity=LeanObservationIdentity(
            observation_contract=ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
            semantic_compatibility_id=SemanticCompatibilityId("sha256:" + ("00" * 32)),
        ),
        accum_score_policy=request.accum_score_policy,
        signal_engine_config=request.signal_engine_config,
        structural_gates=request.structural_gates,
        execution_gates=request.execution_gates,
        hard_filter_policy=request.hard_filter_policy,
        unevaluable_gate_policy=request.unevaluable_gate_policy,
        created_at=NOW,
        source_revision=SOURCE_REVISION,
    )
    with pytest.raises(LearningContractError, match="compatibility_id mismatch"):
        EnsureAccumulationPolicySnapshotsUseCase(repo).execute(bad)


def test_ensure_rejects_empty_source_revision() -> None:
    repo = _MemoryPolicySnapshotRepo()
    with pytest.raises(LearningContractError, match="source_revision"):
        EnsureAccumulationPolicySnapshotsUseCase(repo).execute(_request(source_revision=""))


def test_mismatched_identity_writes_nothing() -> None:
    """Fail closed *before* any row lands, not part-way through the eight."""
    repo = _MemoryPolicySnapshotRepo()
    request = _request()
    bad = replace(
        request,
        observation_identity=LeanObservationIdentity(
            observation_contract=ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
            semantic_compatibility_id=SemanticCompatibilityId("sha256:" + ("11" * 32)),
        ),
    )
    with pytest.raises(LearningContractError, match="compatibility_id mismatch"):
        EnsureAccumulationPolicySnapshotsUseCase(repo).execute(bad)

    assert repo.rows == {}
    assert repo.batch_calls == []


def test_typed_material_change_forks_the_cohort_instead_of_colliding() -> None:
    """ADR-068 turns the old under-forking failure into a clean fork.

    Before ADR-068 a typed policy change with unchanged config bytes produced the
    *same* ``compatibility_id``, so the same ``snapshot_id`` was recomputed with a
    different payload digest and the immutable-artifact conflict was the only
    thing standing between that change and a silently pooled cohort. The snapshot
    payload digest is now identity-material, so the changed policy lands in its
    own cohort and the conflict is structurally unreachable — the under-forking it
    used to catch cannot occur.
    """
    base = AccumScorePolicy()
    accum_mutated = replace(base, consistency=replace(base.consistency, weight=40.0))

    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    first = use_case.execute(_request(accum=base))
    second = use_case.execute(_request(accum=accum_mutated))

    assert first.compatibility_id != second.compatibility_id
    assert set(first.snapshot_ids).isdisjoint(second.snapshot_ids)
    assert len(repo.rows) == 16


def test_declared_policy_change_forks_compatibility_id() -> None:
    """The declared-policy axis of ADR-068 §1, exercised through the use case."""
    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    a = use_case.execute(_request())
    b = use_case.execute(_request(hard_filter=replace(_default_hard_filters(), min_piotroski=7)))
    assert a.compatibility_id != b.compatibility_id
    assert len(repo.rows) == 16


def test_material_config_hash_is_the_resolved_policy_fold() -> None:
    """The row column and the cohort must never describe different policy.

    ADR-068 repoints ``material_config_hash`` from a hash of raw config bytes to
    the same eight-row payload fold that feeds the declared-policy axis of the
    cohort id, so the two can no longer drift apart.
    """
    repo = _MemoryPolicySnapshotRepo()
    identity = resolve_accumulation_cohort_identity(
        accum_score_policy=AccumScorePolicy(),
        signal_engine_config=SignalEngineConfig(),
        structural_gates=[FundamentalGate(), LiquidityGate()],
        execution_gates=[BandarGate()],
        hard_filter_policy=_default_hard_filters(),
        unevaluable_gate_policy=UnevaluableGatePolicy(),
    )
    EnsureAccumulationPolicySnapshotsUseCase(repo).execute(_request())

    expected = "sha256:" + identity.policy_snapshot_payload_digest
    assert {r.material_config_hash for r in repo.rows.values()} == {expected}


def test_created_at_change_does_not_affect_digest() -> None:
    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    use_case.execute(_request(created_at=NOW, source_revision=SOURCE_REVISION))
    response = use_case.execute(
        _request(
            created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
            source_revision=SOURCE_REVISION,
        )
    )
    assert response.inserted_count == 0
    assert response.reused_count == 8


def test_unevaluable_gate_policy_change_forks_the_cohort() -> None:
    """The eighth row is real identity, not decoration.

    ``surface`` and ``block`` reject different candidates on missing gate input
    (``assess_risk_gate_evaluator.evaluate``), so two deployments that differ
    only there must land in different cohorts. Before this row existed they
    collided on one ``compatibility_id`` while pooling incomparable decisions.
    """
    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    surfacing = use_case.execute(_request())
    blocking = use_case.execute(
        _request(
            unevaluable=UnevaluableGatePolicy(
                action=UnevaluableGateAction.BLOCK, block_confidence=70
            )
        )
    )

    assert surfacing.compatibility_id != blocking.compatibility_id
    assert set(surfacing.snapshot_ids).isdisjoint(blocking.snapshot_ids)
    assert len(repo.rows) == 16
    by_compat = {
        r.compatibility_id
        for r in repo.rows.values()
        if r.policy_id == PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY
    }
    assert len(by_compat) == 2


def test_block_confidence_alone_forks_the_cohort() -> None:
    """Both serialized fields are identity, not only ``action``."""
    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    low = use_case.execute(
        _request(
            unevaluable=UnevaluableGatePolicy(
                action=UnevaluableGateAction.BLOCK, block_confidence=10
            )
        )
    )
    high = use_case.execute(
        _request(
            unevaluable=UnevaluableGatePolicy(
                action=UnevaluableGateAction.BLOCK, block_confidence=90
            )
        )
    )
    assert low.compatibility_id != high.compatibility_id
