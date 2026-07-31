"""Tests for EnsureAccumulationPolicySnapshotsUseCase (ADR-059)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Sequence

import pytest

from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
    resolve_lean_semantic_compatibility_id,
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
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    AssessmentPurpose,
    LearningContractError,
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


def _identity(canonical: str) -> LeanObservationIdentity:
    return LeanObservationIdentity(
        observation_contract=ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
        semantic_compatibility_id=resolve_lean_semantic_compatibility_id(canonical),
    )


def _request(
    *,
    canonical: str = "resolved-config-v1",
    accum: AccumScorePolicy | None = None,
    signal: SignalEngineConfig | None = None,
    created_at: datetime = NOW,
    source_revision: str = SOURCE_REVISION,
) -> EnsureAccumulationPolicySnapshotsRequest:
    return EnsureAccumulationPolicySnapshotsRequest(
        resolved_config_canonical=canonical,
        verified_config_canonical=canonical,
        observation_identity=_identity(canonical),
        accum_score_policy=accum or AccumScorePolicy(),
        signal_engine_config=signal or SignalEngineConfig(),
        structural_gates=[FundamentalGate(), LiquidityGate()],
        execution_gates=[BandarGate()],
        created_at=created_at,
        source_revision=source_revision,
    )


def test_ensure_writes_exactly_six_closed_policy_ids() -> None:
    repo = _MemoryPolicySnapshotRepo()
    response = EnsureAccumulationPolicySnapshotsUseCase(repo).execute(_request())

    assert response.inserted_count == 6
    assert response.reused_count == 0
    assert response.required_policy_ids == ACCUMULATION_PRODUCTION_POLICY_IDS
    assert len(repo.rows) == 6
    assert len(repo.batch_calls) == 1
    assert len(repo.batch_calls[0]) == 6
    written_ids = {r.policy_id for r in repo.rows.values()}
    assert written_ids == set(ACCUMULATION_PRODUCTION_POLICY_IDS)
    for snap in repo.rows.values():
        assert snap.source_revision == SOURCE_REVISION


def test_ensure_is_idempotent_for_same_cohort_content() -> None:
    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    first = use_case.execute(_request())
    second = use_case.execute(_request())

    assert first.inserted_count == 6
    assert second.inserted_count == 0
    assert second.reused_count == 6
    assert len(repo.rows) == 6
    assert len(repo.batch_calls) == 2


def test_ensure_rejects_compatibility_mismatch() -> None:
    repo = _MemoryPolicySnapshotRepo()
    request = _request(canonical="cfg-a")
    bad = EnsureAccumulationPolicySnapshotsRequest(
        resolved_config_canonical="cfg-a",
        verified_config_canonical="cfg-a",
        observation_identity=LeanObservationIdentity(
            observation_contract=ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
            semantic_compatibility_id=SemanticCompatibilityId("sha256:" + ("00" * 32)),
        ),
        accum_score_policy=request.accum_score_policy,
        signal_engine_config=request.signal_engine_config,
        structural_gates=request.structural_gates,
        execution_gates=request.execution_gates,
        created_at=NOW,
        source_revision=SOURCE_REVISION,
    )
    with pytest.raises(LearningContractError, match="compatibility_id mismatch"):
        EnsureAccumulationPolicySnapshotsUseCase(repo).execute(bad)


def test_ensure_rejects_empty_source_revision() -> None:
    repo = _MemoryPolicySnapshotRepo()
    with pytest.raises(LearningContractError, match="source_revision"):
        EnsureAccumulationPolicySnapshotsUseCase(repo).execute(_request(source_revision=""))


def test_ensure_rejects_config_generation_change_before_any_write() -> None:
    repo = _MemoryPolicySnapshotRepo()
    request = replace(_request(canonical="cfg-a"), verified_config_canonical="cfg-b")

    with pytest.raises(LearningContractError, match="configuration changed"):
        EnsureAccumulationPolicySnapshotsUseCase(repo).execute(request)

    assert repo.rows == {}
    assert repo.batch_calls == []


def test_typed_material_change_same_cohort_fails_closed() -> None:
    base = AccumScorePolicy()
    accum_mutated = replace(base, consistency=replace(base.consistency, weight=40.0))

    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    use_case.execute(_request(canonical="cfg-1", accum=base))
    with pytest.raises(LearningContractError, match="immutable artifact conflict"):
        use_case.execute(_request(canonical="cfg-1", accum=accum_mutated))
    # Atomic failure must not leave partial conflict-side rows; original set remains.
    assert len(repo.rows) == 6


def test_resolved_config_change_forks_compatibility_id() -> None:
    repo = _MemoryPolicySnapshotRepo()
    use_case = EnsureAccumulationPolicySnapshotsUseCase(repo)
    a = use_case.execute(_request(canonical="cfg-1"))
    b = use_case.execute(_request(canonical="cfg-2"))
    assert a.compatibility_id != b.compatibility_id
    assert len(repo.rows) == 12


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
    assert response.reused_count == 6
