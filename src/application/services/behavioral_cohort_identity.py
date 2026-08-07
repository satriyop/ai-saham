"""ADR-068 authoritative cohort identity for ``ACCUMULATION_DISCOVERY``.

Layer: Application (pure policy; the probe run it drives performs no IO)

A cohort (``compatibility_id``) answers exactly one question: *would this engine
give the same answer to the same input?* ADR-068 §1 replaces the three proxies
that used to approximate it (raw config bytes, hand-typed engine version
constants, and the write-only ``config_hash``) with a fold of three orthogonal,
directly measured parts:

===========================  =========================================
Part                         Question it answers
===========================  =========================================
behavioural probe digest     does the engine answer the same?
ADR-059 snapshot payload     is the declared policy the same?
payload schema version       is the stored record the same shape?
===========================  =========================================

Nothing else. No config bytes, no hand-typed engine versions, and no fallback
to either — ADR-068 §7 is a clean break with no dual-identity path.

``contract_id`` in the hashed material is formula framing, not a fourth part:
it names *which* fold produced a digest so two different formulas can never
collide on one value. It is fixed for the lifetime of the formula and is never
bumped to express a behaviour or policy change; those move the parts above.

Why this module replaces the slice-3 shadow resolver
----------------------------------------------------

``shadow_behavioral_cohort_identity`` deliberately degraded a failed probe run
to a typed unavailable result, because at that point every value it produced
was diagnostic and blocking the corpus on a broken diagnostic would have been
worse than the defect. That trade inverts here: the probe digest *is* the
identity, so a probe failure must fail the capture closed rather than mint an
identity that is missing its code axis. There is deliberately no ``except``
in this module.

Failure semantics
-----------------

Every failure propagates. A broken probe run, an incomplete policy payload set,
or a malformed payload raises, and the corpus write never happens.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.application.services.accumulation_policy_snapshot_payloads import (
    build_all_accumulation_policy_payloads,
)
from src.application.services.accumulation_screen_hard_filter_policy import (
    AccumulationScreenHardFilterPolicy,
)
from src.application.services.behavioral_probe_runner import (
    compute_behavioral_probe_digest,
)
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.score_accum_use_case import AccumScorePolicy
from src.domain.rules.risk_gate import RiskGate, UnevaluableGatePolicy
from src.domain.value_objects.learning_artifacts import (
    ACCUMULATION_PRODUCTION_POLICY_IDS,
    LearningContractError,
    canonical_json,
    policy_snapshot_payload_digest,
)
from src.domain.value_objects.signal_artifact_identity import SemanticCompatibilityId
from src.domain.value_objects.signal_artifact_schema import (
    ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION,
)

# Framing label for the fold below. Identifies the formula, never the engine.
BEHAVIORAL_ACCUMULATION_COMPATIBILITY_CONTRACT_ID = "behavioral_accumulation_compatibility.v1"


@dataclass(frozen=True)
class AccumulationCohortIdentity:
    """The resolved cohort tag plus the three parts it was folded from.

    The parts are carried beside the id so an operator can attribute a moved
    cohort to an axis (code, declared policy, record shape) without rerunning
    anything. They are reporting values: ``semantic_compatibility_id`` is the
    only field any writer persists as identity.
    """

    semantic_compatibility_id: SemanticCompatibilityId
    behavioral_probe_digest: str
    policy_snapshot_payload_digest: str
    observation_payload_schema_version: int


def compute_policy_snapshot_set_digest(
    policy_snapshot_payloads: Mapping[str, Mapping[str, Any]],
) -> str:
    """Fold the closed ADR-059 v4 nine-row payload set into one digest.

    Consumes the existing per-row ``policy_snapshot_payload_digest`` rather than
    inventing a second hashing scheme, so a row's identity digest and its
    contribution to the cohort are the same number.

    Fails closed when the set is not exactly ``ACCUMULATION_PRODUCTION_POLICY_IDS``:
    a missing or extra policy row means the declared-policy axis was measured
    over something other than the production closed set.
    """
    if set(policy_snapshot_payloads) != set(ACCUMULATION_PRODUCTION_POLICY_IDS):
        raise LearningContractError(
            "cohort identity requires exactly the closed v4 policy set "
            f"{sorted(ACCUMULATION_PRODUCTION_POLICY_IDS)}, got "
            f"{sorted(policy_snapshot_payloads)}"
        )
    per_policy = {
        policy_id: policy_snapshot_payload_digest(policy_snapshot_payloads[policy_id])
        for policy_id in ACCUMULATION_PRODUCTION_POLICY_IDS
    }
    return hashlib.sha256(canonical_json(per_policy).encode("utf-8")).hexdigest()


def resolve_accumulation_cohort_identity_from_payloads(
    *,
    policy_snapshot_payloads: Mapping[str, Mapping[str, Any]],
) -> AccumulationCohortIdentity:
    """Fold the three ADR-068 parts into the authoritative cohort identity.

    The single place the formula exists. Deterministic: the same code, the same
    resolved policies, and the same payload schema version always produce the
    same id.
    """
    probe_digest = compute_behavioral_probe_digest()
    snapshot_digest = compute_policy_snapshot_set_digest(policy_snapshot_payloads)
    material = canonical_json(
        {
            "contract_id": BEHAVIORAL_ACCUMULATION_COMPATIBILITY_CONTRACT_ID,
            "behavioral_probe_digest": probe_digest,
            "policy_snapshot_payload_digest": snapshot_digest,
            "observation_payload_schema_version": (ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION),
        }
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return AccumulationCohortIdentity(
        semantic_compatibility_id=SemanticCompatibilityId("sha256:" + digest),
        behavioral_probe_digest=probe_digest,
        policy_snapshot_payload_digest=snapshot_digest,
        observation_payload_schema_version=ACCUMULATION_OBSERVATION_PAYLOAD_SCHEMA_VERSION,
    )


def resolve_accumulation_cohort_identity(
    *,
    accum_score_policy: AccumScorePolicy,
    signal_engine_config: SignalEngineConfig,
    structural_gates: Sequence[RiskGate],
    execution_gates: Sequence[RiskGate],
    hard_filter_policy: AccumulationScreenHardFilterPolicy,
    unevaluable_gate_policy: UnevaluableGatePolicy,
) -> AccumulationCohortIdentity:
    """Resolve cohort identity from the same typed policies the engines receive.

    Builds the ADR-059 payloads from the resolved typed objects — never from a
    YAML re-parse — so a comment or formatting edit cannot move identity while a
    changed declared value must.
    """
    return resolve_accumulation_cohort_identity_from_payloads(
        policy_snapshot_payloads=build_all_accumulation_policy_payloads(
            accum_score_policy=accum_score_policy,
            signal_engine_config=signal_engine_config,
            structural_gates=structural_gates,
            execution_gates=execution_gates,
            hard_filter_policy=hard_filter_policy,
            unevaluable_gate_policy=unevaluable_gate_policy,
        )
    )
