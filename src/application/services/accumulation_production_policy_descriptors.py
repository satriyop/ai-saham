"""Authoritative production-policy snapshot descriptors (ADR-059 v4).

Layer: Application (pure). Single source of truth for decision_type,
semantic_engine_contract_id, and policy_version per closed-set policy_id.
Used by ensure-write and readiness verification so they cannot drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.application.services.accumulation_policy_snapshot_payloads import (
    ACCUM_SCORE_SEMANTIC_CONTRACT_ID,
    HARD_FILTERS_SEMANTIC_CONTRACT_ID,
    RISK_HARD_GATES_SEMANTIC_CONTRACT_ID,
    SIGNAL_DECISION_POLICY_SEMANTIC_CONTRACT_ID,
    SIGNAL_SEMANTIC_CONTRACT_ID,
    UNEVALUABLE_GATE_POLICY_SEMANTIC_CONTRACT_ID,
)
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS_V3,
    ACCUMULATION_PRODUCTION_POLICY_IDS_V4,
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
    PRODUCTION_POLICY_ID_RISK_HARD_GATES,
    PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION,
    PRODUCTION_POLICY_ID_SIGNAL_DECISION_POLICY,
    PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS,
    PRODUCTION_POLICY_ID_SIGNAL_FLAGS,
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE,
    PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY,
    PRODUCTION_POLICY_VERSION_V1,
)


@dataclass(frozen=True)
class ProductionPolicyDescriptor:
    """Immutable production identity expectations for one policy_id row."""

    policy_id: str
    decision_type: str
    semantic_engine_contract_id: str
    policy_version: str = PRODUCTION_POLICY_VERSION_V1


# Closed active set descriptors (production_policy_snapshot.v4).
ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V4: Mapping[str, ProductionPolicyDescriptor] = {
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
        decision_type="score",
        semantic_engine_contract_id=ACCUM_SCORE_SEMANTIC_CONTRACT_ID,
    ),
    PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS,
        decision_type="score",
        semantic_engine_contract_id=SIGNAL_SEMANTIC_CONTRACT_ID,
    ),
    PRODUCTION_POLICY_ID_SIGNAL_FLAGS: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_SIGNAL_FLAGS,
        decision_type="score",
        semantic_engine_contract_id=SIGNAL_SEMANTIC_CONTRACT_ID,
    ),
    PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION,
        decision_type="score",
        semantic_engine_contract_id=SIGNAL_SEMANTIC_CONTRACT_ID,
    ),
    PRODUCTION_POLICY_ID_RISK_HARD_GATES: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_RISK_HARD_GATES,
        decision_type="gate",
        semantic_engine_contract_id=RISK_HARD_GATES_SEMANTIC_CONTRACT_ID,
    ),
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE,
        decision_type="score",
        semantic_engine_contract_id=SIGNAL_SEMANTIC_CONTRACT_ID,
    ),
    PRODUCTION_POLICY_ID_HARD_FILTERS: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_HARD_FILTERS,
        decision_type="gate",
        semantic_engine_contract_id=HARD_FILTERS_SEMANTIC_CONTRACT_ID,
    ),
    PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_UNEVALUABLE_GATE_POLICY,
        decision_type="gate",
        semantic_engine_contract_id=UNEVALUABLE_GATE_POLICY_SEMANTIC_CONTRACT_ID,
    ),
    PRODUCTION_POLICY_ID_SIGNAL_DECISION_POLICY: ProductionPolicyDescriptor(
        policy_id=PRODUCTION_POLICY_ID_SIGNAL_DECISION_POLICY,
        decision_type="gate",
        semantic_engine_contract_id=SIGNAL_DECISION_POLICY_SEMANTIC_CONTRACT_ID,
    ),
}

# Immutable historical descriptor set retained for audit/tests only.
ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V3: Mapping[str, ProductionPolicyDescriptor] = {
    policy_id: ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V4[policy_id]
    for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS_V3
}

# Ordered closed set must match ACCUMULATION_PRODUCTION_POLICY_IDS_V4 exactly.
assert tuple(ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V4) == tuple(
    # Mapping preserves insertion order (3.7+); lock against set drift.
    pid
    for pid in ACCUMULATION_PRODUCTION_POLICY_IDS_V4
), "descriptor map keys must match closed v4 policy order/set"


def decision_type_by_policy() -> dict[str, str]:
    return {
        pid: d.decision_type for pid, d in ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V4.items()
    }


def semantic_contract_by_policy() -> dict[str, str]:
    return {
        pid: d.semantic_engine_contract_id
        for pid, d in ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V4.items()
    }
