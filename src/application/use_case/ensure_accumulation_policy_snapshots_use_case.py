"""Ensure cohort-bound production policy snapshots before observation writes.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from src.application.services.accumulation_policy_snapshot_payloads import (
    ACCUM_SCORE_SEMANTIC_CONTRACT_ID,
    RISK_HARD_GATES_SEMANTIC_CONTRACT_ID,
    SIGNAL_SEMANTIC_CONTRACT_ID,
    build_all_accumulation_policy_payloads,
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
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_RISK_HARD_GATES,
    PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION,
    PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS,
    PRODUCTION_POLICY_ID_SIGNAL_FLAGS,
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE,
    PRODUCTION_POLICY_VERSION_V1,
    AssessmentPurpose,
    LearningContractError,
    LearningContractId,
    ProductionPolicySnapshot,
    material_config_hash_from_canonical,
)
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
)

_DECISION_TYPE_BY_POLICY: dict[str, str] = {
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS: "score",
    PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS: "score",
    PRODUCTION_POLICY_ID_SIGNAL_FLAGS: "score",
    PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION: "score",
    PRODUCTION_POLICY_ID_RISK_HARD_GATES: "gate",
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE: "score",
}

_SEMANTIC_CONTRACT_BY_POLICY: dict[str, str] = {
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS: ACCUM_SCORE_SEMANTIC_CONTRACT_ID,
    PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS: SIGNAL_SEMANTIC_CONTRACT_ID,
    PRODUCTION_POLICY_ID_SIGNAL_FLAGS: SIGNAL_SEMANTIC_CONTRACT_ID,
    PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION: SIGNAL_SEMANTIC_CONTRACT_ID,
    PRODUCTION_POLICY_ID_RISK_HARD_GATES: RISK_HARD_GATES_SEMANTIC_CONTRACT_ID,
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE: SIGNAL_SEMANTIC_CONTRACT_ID,
}


@dataclass(frozen=True)
class EnsureAccumulationPolicySnapshotsRequest:
    resolved_config_canonical: str
    observation_identity: LeanObservationIdentity
    accum_score_policy: AccumScorePolicy
    signal_engine_config: SignalEngineConfig
    structural_gates: Sequence[RiskGate]
    execution_gates: Sequence[RiskGate]
    created_at: datetime
    source_revision: str = ""


@dataclass(frozen=True)
class EnsureAccumulationPolicySnapshotsResponse:
    compatibility_id: str
    required_policy_ids: tuple[str, ...]
    inserted_count: int
    reused_count: int
    snapshot_ids: tuple[str, ...]


class EnsureAccumulationPolicySnapshotsUseCase:
    """Materialize the closed v1 set of production policy snapshots for a cohort.

    Must run before any accumulation observation write. Recomputes lean
    compatibility from the supplied config bytes and fails closed on mismatch
    or under-forked same-key digest conflict.
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
        )
        if set(payloads) != set(ACCUMULATION_PRODUCTION_POLICY_IDS):
            raise LearningContractError(
                "payload builder must emit exactly the closed v1 policy set"
            )

        learning_observation_contract_id = LearningContractId.ACCUMULATION_OBSERVATION.value
        inserted = 0
        reused = 0
        snapshot_ids: list[str] = []

        for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS:
            snapshot = ProductionPolicySnapshot.create(
                purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                learning_observation_contract_id=learning_observation_contract_id,
                producer_observation_contract=ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
                compatibility_id=compatibility_id,
                policy_id=policy_id,
                policy_version=PRODUCTION_POLICY_VERSION_V1,
                decision_type=_DECISION_TYPE_BY_POLICY[policy_id],
                semantic_engine_contract_id=_SEMANTIC_CONTRACT_BY_POLICY[policy_id],
                material_config_hash=material_hash,
                canonical_payload=payloads[policy_id],
                source_revision=request.source_revision,
                created_at=request.created_at,
            )
            wrote = self._repository.add_policy_snapshot(snapshot)
            if wrote:
                inserted += 1
            else:
                reused += 1
            snapshot_ids.append(snapshot.snapshot_id)

        return EnsureAccumulationPolicySnapshotsResponse(
            compatibility_id=compatibility_id,
            required_policy_ids=ACCUMULATION_PRODUCTION_POLICY_IDS,
            inserted_count=inserted,
            reused_count=reused,
            snapshot_ids=tuple(snapshot_ids),
        )
