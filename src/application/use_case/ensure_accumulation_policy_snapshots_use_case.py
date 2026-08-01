"""Ensure cohort-bound production policy snapshots before observation writes.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from src.application.services.accumulation_policy_snapshot_payloads import (
    build_all_accumulation_policy_payloads,
)
from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2,
)
from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
)
from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
    resolve_lean_semantic_compatibility_id,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.ports.learning_artifact_repositories import (
    LearningPolicySnapshotRepository,
)
from src.domain.rules.risk_gate import RiskGate
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    AssessmentPurpose,
    LearningContractError,
    LearningContractId,
    ProductionPolicySnapshot,
    material_config_hash_from_canonical,
)
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
)


@dataclass(frozen=True)
class EnsureAccumulationPolicySnapshotsRequest:
    resolved_config_canonical: str
    verified_config_canonical: str
    observation_identity: LeanObservationIdentity
    accum_score_policy: AccumScorePolicy
    signal_engine_config: SignalEngineConfig
    structural_gates: Sequence[RiskGate]
    execution_gates: Sequence[RiskGate]
    hard_filter_policy: AccumulationScreenHardFilterPolicy
    created_at: datetime
    source_revision: str


@dataclass(frozen=True)
class EnsureAccumulationPolicySnapshotsResponse:
    compatibility_id: str
    required_policy_ids: tuple[str, ...]
    inserted_count: int
    reused_count: int
    snapshot_ids: tuple[str, ...]


class EnsureAccumulationPolicySnapshotsUseCase:
    """Materialize the closed v2 set of production policy snapshots for a cohort.

    Must run before any accumulation observation write. Recomputes lean
    compatibility from the supplied config bytes and fails closed on mismatch
    or under-forked same-key digest conflict. Writes only
    ``production_policy_snapshot.v2`` (seven rows). No dual-write of v1.
    """

    def __init__(self, repository: LearningPolicySnapshotRepository) -> None:
        self._repository = repository

    def execute(
        self, request: EnsureAccumulationPolicySnapshotsRequest
    ) -> EnsureAccumulationPolicySnapshotsResponse:
        if request.resolved_config_canonical != request.verified_config_canonical:
            raise LearningContractError(
                "material configuration changed while production policies were "
                "being resolved; retry capture/backfill"
            )
        if (
            request.observation_identity.observation_contract
            != ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT
        ):
            raise LearningContractError(
                "production policy snapshots require "
                f"{ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT!r}, got "
                f"{request.observation_identity.observation_contract!r}"
            )

        recomputed = resolve_lean_semantic_compatibility_id(request.resolved_config_canonical)
        supplied = request.observation_identity.semantic_compatibility_id
        if str(recomputed) != str(supplied):
            raise LearningContractError(
                "lean compatibility_id mismatch: recomputed "
                f"{recomputed!s} != supplied {supplied!s}"
            )

        compatibility_id = str(supplied)
        material_hash = material_config_hash_from_canonical(request.resolved_config_canonical)
        payloads = build_all_accumulation_policy_payloads(
            accum_score_policy=request.accum_score_policy,
            signal_engine_config=request.signal_engine_config,
            structural_gates=request.structural_gates,
            execution_gates=request.execution_gates,
            hard_filter_policy=request.hard_filter_policy,
        )
        if set(payloads) != set(ACCUMULATION_PRODUCTION_POLICY_IDS):
            raise LearningContractError(
                "payload builder must emit exactly the closed v2 policy set"
            )

        if not request.source_revision.strip():
            raise LearningContractError("source_revision must be non-empty producer provenance")

        learning_observation_contract_id = LearningContractId.ACCUMULATION_OBSERVATION.value
        snapshots: list[ProductionPolicySnapshot] = []
        for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS:
            descriptor = ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2[policy_id]
            snapshots.append(
                ProductionPolicySnapshot.create(
                    contract_id=LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
                    purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                    learning_observation_contract_id=learning_observation_contract_id,
                    producer_observation_contract=ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
                    compatibility_id=compatibility_id,
                    policy_id=policy_id,
                    policy_version=descriptor.policy_version,
                    decision_type=descriptor.decision_type,
                    semantic_engine_contract_id=descriptor.semantic_engine_contract_id,
                    material_config_hash=material_hash,
                    canonical_payload=payloads[policy_id],
                    source_revision=request.source_revision,
                    created_at=request.created_at,
                )
            )

        # Single atomic write: conflict on any row rolls back the whole set.
        inserted, reused = self._repository.add_policy_snapshots_atomic(snapshots)

        return EnsureAccumulationPolicySnapshotsResponse(
            compatibility_id=compatibility_id,
            required_policy_ids=ACCUMULATION_PRODUCTION_POLICY_IDS,
            inserted_count=inserted,
            reused_count=reused,
            snapshot_ids=tuple(s.snapshot_id for s in snapshots),
        )
