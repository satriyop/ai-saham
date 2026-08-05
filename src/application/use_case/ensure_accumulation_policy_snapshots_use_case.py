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
from src.application.services.behavioral_cohort_identity import (
    resolve_accumulation_cohort_identity_from_payloads,
)
from src.application.services.lean_observation_identity import (
    LeanObservationIdentity,
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
)
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
)


@dataclass(frozen=True)
class EnsureAccumulationPolicySnapshotsRequest:
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

    Must run before any accumulation observation write. Recomputes the ADR-068
    behavioural cohort identity from the payloads it is about to write and fails
    closed on mismatch with the identity the caller already stamped on its
    observations. Writes only ``production_policy_snapshot.v2`` (seven rows). No
    dual-write of v1.

    ADR-068 removed the config-byte double-read this use case used to perform.
    The guarantee it bought is now structural rather than checked: identity is
    derived from the same resolved typed policy objects the engines received and
    the snapshot rows serialize, so a config file edited mid-run cannot produce
    an identity that disagrees with the policies actually used.
    """

    def __init__(self, repository: LearningPolicySnapshotRepository) -> None:
        self._repository = repository

    def execute(
        self, request: EnsureAccumulationPolicySnapshotsRequest
    ) -> EnsureAccumulationPolicySnapshotsResponse:
        if (
            request.observation_identity.observation_contract
            != ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT
        ):
            raise LearningContractError(
                "production policy snapshots require "
                f"{ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT!r}, got "
                f"{request.observation_identity.observation_contract!r}"
            )

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

        identity = resolve_accumulation_cohort_identity_from_payloads(
            policy_snapshot_payloads=payloads
        )
        supplied = request.observation_identity.semantic_compatibility_id
        if str(identity.semantic_compatibility_id) != str(supplied):
            raise LearningContractError(
                "behavioural compatibility_id mismatch: recomputed "
                f"{identity.semantic_compatibility_id!s} != supplied {supplied!s}"
            )

        compatibility_id = str(supplied)
        # Hash of the resolved material policy set, not of raw config bytes.
        # Same fold that feeds the declared-policy axis of the cohort id, so the
        # row column and the cohort can never describe different policy.
        material_hash = "sha256:" + identity.policy_snapshot_payload_digest

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
