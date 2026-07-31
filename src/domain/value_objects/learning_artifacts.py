"""Pure schema-v1 contracts for database-owned learning artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Mapping

LEARNING_SCHEMA_VERSION = 1


class LearningContractError(ValueError):
    """Raised when a learning artifact violates its immutable contract."""


class AssessmentPurpose(str, Enum):
    ACCUMULATION_DISCOVERY = "ACCUMULATION_DISCOVERY"
    PRE_OPEN_AUCTION_DIRECTION = "PRE_OPEN_AUCTION_DIRECTION"
    SWING_TRADE_SETUP = "SWING_TRADE_SETUP"


class EvaluationMethod(str, Enum):
    FORWARD_OUTCOME_COHORT = "FORWARD_OUTCOME_COHORT"
    SESSION_OUTCOME_COHORT = "SESSION_OUTCOME_COHORT"
    PORTFOLIO_WALK_FORWARD = "PORTFOLIO_WALK_FORWARD"


class OutcomeBasis(str, Enum):
    PRICE_PATH_ONLY = "PRICE_PATH_ONLY"
    SIMULATED_NET_EXECUTION = "SIMULATED_NET_EXECUTION"
    REALIZED_TRADE = "REALIZED_TRADE"


class EvaluationReadiness(str, Enum):
    INELIGIBLE = "INELIGIBLE"
    DESCRIPTIVE_READY = "DESCRIPTIVE_READY"
    OOS_DIAGNOSTIC_READY = "OOS_DIAGNOSTIC_READY"
    POLICY_REVIEW_ELIGIBLE = "POLICY_REVIEW_ELIGIBLE"


class LabelAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ValidationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class LearningContractId(str, Enum):
    # ADR-056: accum observation unit is ticker-session (v2 payload).
    ACCUMULATION_OBSERVATION = "learning_observation.accumulation_discovery.v2"
    PRE_OPEN_OBSERVATION = "learning_observation.pre_open_auction_direction.v1"
    # Accum path labels only (no tactical/swing brand on this corpus).
    ACCUM_3D_LABEL = "price_path.accum_3d.v1"
    ACCUM_10D_LABEL = "price_path.accum_10d.v1"
    ACCUM_20D_LABEL = "price_path.accum_20d.v1"
    PRE_OPEN_LABEL = "price_path.open_30m.v1"
    ACCUMULATION_EVALUATION = "forward_outcome_cohort.v1"
    PRE_OPEN_EVALUATION = "session_outcome_cohort.v1"
    SWING_EVALUATION = "portfolio_walk_forward.v1"
    SWING_PROPOSAL = "swing_policy_proposal.v1"
    SWING_VALIDATION = "paired_oos_swing_policy_validation.v1"
    YAML_APPLICATION = "yaml_policy_application.v1"


_OBSERVATION_CONTRACT_BY_PURPOSE = MappingProxyType(
    {
        AssessmentPurpose.ACCUMULATION_DISCOVERY: LearningContractId.ACCUMULATION_OBSERVATION,
        AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION: LearningContractId.PRE_OPEN_OBSERVATION,
    }
)
_EVALUATION_CONTRACT_BY_METHOD = MappingProxyType(
    {
        EvaluationMethod.FORWARD_OUTCOME_COHORT: LearningContractId.ACCUMULATION_EVALUATION,
        EvaluationMethod.SESSION_OUTCOME_COHORT: LearningContractId.PRE_OPEN_EVALUATION,
        EvaluationMethod.PORTFOLIO_WALK_FORWARD: LearningContractId.SWING_EVALUATION,
    }
)
_PURPOSE_METHOD = MappingProxyType(
    {
        AssessmentPurpose.ACCUMULATION_DISCOVERY: EvaluationMethod.FORWARD_OUTCOME_COHORT,
        AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION: EvaluationMethod.SESSION_OUTCOME_COHORT,
        AssessmentPurpose.SWING_TRADE_SETUP: EvaluationMethod.PORTFOLIO_WALK_FORWARD,
    }
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise LearningContractError("learning timestamps must be timezone-aware")
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise LearningContractError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Return deterministic JSON for identity and immutable payload hashing."""

    return json.dumps(
        _json_value(payload),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_learning_id(contract_id: LearningContractId, identity: Mapping[str, Any]) -> str:
    """Hash contract plus relational identity, rejecting operational timestamps."""

    if "captured_at" in identity:
        raise LearningContractError("captured_at must not participate in relational identity")
    material = canonical_json({"contract_id": contract_id, "identity": identity})
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def artifact_digest(payload: Mapping[str, Any]) -> str:
    """Hash an artifact's complete immutable content."""

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _require_non_empty(name: str, value: str) -> None:
    if not value.strip():
        raise LearningContractError(f"{name} must be non-empty")


def _artifact_payload(value: Any, *, id_field: str, digest_field: str) -> dict[str, Any]:
    """Return the immutable content a digest is computed over.

    Identity and the digest itself are dropped, then whatever the artifact
    declares in ``DIGEST_EXCLUDED_FIELDS``. Popping is strict so a stale
    declaration fails loudly instead of silently widening the hash.

    Changing what this returns changes every future digest while leaving stored
    rows on the old rule. Treat any edit as a schema bump: see
    ``tests/domain/value_objects/test_learning_artifact_digest_contract.py``.
    """

    payload = asdict(value)
    payload.pop(id_field)
    payload.pop(digest_field)
    for operational_field in type(value).DIGEST_EXCLUDED_FIELDS:
        payload.pop(operational_field)
    return payload


def validate_artifact_integrity(
    value: Any, *, id_field: str, digest_field: str = "artifact_digest"
) -> None:
    """Reject a DTO whose immutable payload no longer matches its digest."""

    expected = artifact_digest(
        _artifact_payload(value, id_field=id_field, digest_field=digest_field)
    )
    actual = getattr(value, digest_field)
    if actual != expected:
        raise LearningContractError("learning artifact digest does not match its payload")


@dataclass(frozen=True)
class LearningObservation:
    # Nothing excluded: captured_at does participate in this artifact's digest.
    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    observation_id: str
    artifact_digest: str
    schema_version: int
    contract_id: LearningContractId
    purpose: AssessmentPurpose
    policy_contract: str
    horizon_contract: str
    compatibility_id: str
    cutoff_at: datetime
    universe_id: str
    window_id: str
    decision_payload: Mapping[str, Any]
    captured_at: datetime

    @classmethod
    def create(
        cls,
        *,
        purpose: AssessmentPurpose,
        policy_contract: str,
        horizon_contract: str,
        compatibility_id: str,
        cutoff_at: datetime,
        universe_id: str,
        window_id: str,
        decision_payload: Mapping[str, Any],
        captured_at: datetime,
    ) -> LearningObservation:
        contract_id = _OBSERVATION_CONTRACT_BY_PURPOSE.get(purpose)
        if contract_id is None:
            raise LearningContractError(f"{purpose.value} has no observation contract")
        for name, value in (
            ("policy_contract", policy_contract),
            ("horizon_contract", horizon_contract),
            ("compatibility_id", compatibility_id),
            ("universe_id", universe_id),
            ("window_id", window_id),
        ):
            _require_non_empty(name, value)
        identity = {
            "purpose": purpose,
            "policy_contract": policy_contract,
            "horizon_contract": horizon_contract,
            "compatibility_id": compatibility_id,
            "cutoff_at": cutoff_at,
            "universe_id": universe_id,
            "window_id": window_id,
        }
        observation_id = stable_learning_id(contract_id, identity)
        draft = cls(
            observation_id=observation_id,
            artifact_digest="",
            schema_version=LEARNING_SCHEMA_VERSION,
            contract_id=contract_id,
            purpose=purpose,
            policy_contract=policy_contract,
            horizon_contract=horizon_contract,
            compatibility_id=compatibility_id,
            cutoff_at=cutoff_at,
            universe_id=universe_id,
            window_id=window_id,
            decision_payload=dict(decision_payload),
            captured_at=captured_at,
        )
        return cls(
            **{
                **asdict(draft),
                "artifact_digest": artifact_digest(
                    _artifact_payload(
                        draft, id_field="observation_id", digest_field="artifact_digest"
                    )
                ),
            }
        )


@dataclass(frozen=True)
class LearningTrackSnapshot:
    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    snapshot_id: str
    artifact_digest: str
    schema_version: int
    observation_id: str
    sampled_at: datetime
    source: str
    snapshot_payload: Mapping[str, Any]
    captured_at: datetime

    @classmethod
    def create(
        cls,
        *,
        observation_id: str,
        sampled_at: datetime,
        source: str,
        snapshot_payload: Mapping[str, Any],
        captured_at: datetime,
    ) -> LearningTrackSnapshot:
        _require_non_empty("observation_id", observation_id)
        _require_non_empty("source", source)
        identity = {
            "observation_id": observation_id,
            "sampled_at": sampled_at,
            "source": source,
        }
        snapshot_id = stable_learning_id(LearningContractId.PRE_OPEN_OBSERVATION, identity)
        draft = cls(
            snapshot_id=snapshot_id,
            artifact_digest="",
            schema_version=LEARNING_SCHEMA_VERSION,
            observation_id=observation_id,
            sampled_at=sampled_at,
            source=source,
            snapshot_payload=dict(snapshot_payload),
            captured_at=captured_at,
        )
        return cls(
            **{
                **asdict(draft),
                "artifact_digest": artifact_digest(
                    _artifact_payload(draft, id_field="snapshot_id", digest_field="artifact_digest")
                ),
            }
        )


@dataclass(frozen=True)
class LearningOutcomeLabel:
    # Identity is (observation_id, contract). labeled_at records when the cron
    # happened to run, so hashing it would make every re-run a digest conflict.
    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset({"labeled_at"})

    label_id: str
    artifact_digest: str
    schema_version: int
    contract_id: LearningContractId
    observation_id: str
    outcome_basis: OutcomeBasis
    availability: LabelAvailability
    outcome: str | None
    metrics: Mapping[str, Any]
    fingerprint: str
    labeled_at: datetime

    @classmethod
    def create(
        cls,
        *,
        contract_id: LearningContractId,
        observation_id: str,
        outcome_basis: OutcomeBasis,
        availability: LabelAvailability,
        outcome: str | None,
        metrics: Mapping[str, Any],
        fingerprint: str,
        labeled_at: datetime,
    ) -> LearningOutcomeLabel:
        if contract_id not in {
            LearningContractId.ACCUM_3D_LABEL,
            LearningContractId.ACCUM_10D_LABEL,
            LearningContractId.ACCUM_20D_LABEL,
            LearningContractId.PRE_OPEN_LABEL,
        }:
            raise LearningContractError("contract_id is not a label contract")
        _require_non_empty("observation_id", observation_id)
        _require_non_empty("fingerprint", fingerprint)
        if availability is LabelAvailability.AVAILABLE and outcome is None:
            raise LearningContractError("available label requires an outcome")
        if availability is LabelAvailability.UNAVAILABLE and outcome is not None:
            raise LearningContractError("unavailable label cannot carry an outcome")
        identity = {"observation_id": observation_id, "contract_id": contract_id}
        label_id = stable_learning_id(contract_id, identity)
        draft = cls(
            label_id=label_id,
            artifact_digest="",
            schema_version=LEARNING_SCHEMA_VERSION,
            contract_id=contract_id,
            observation_id=observation_id,
            outcome_basis=outcome_basis,
            availability=availability,
            outcome=outcome,
            metrics=dict(metrics),
            fingerprint=fingerprint,
            labeled_at=labeled_at,
        )
        return cls(
            **{
                **asdict(draft),
                "artifact_digest": artifact_digest(
                    _artifact_payload(draft, id_field="label_id", digest_field="artifact_digest")
                ),
            }
        )


@dataclass(frozen=True)
class LearningEvaluation:
    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    evaluation_id: str
    artifact_digest: str
    schema_version: int
    contract_id: LearningContractId
    purpose: AssessmentPurpose
    method: EvaluationMethod
    compatibility_id: str
    dataset_fingerprint: str
    split_contract: str
    population: Mapping[str, Any]
    exclusions: Mapping[str, Any]
    metrics: Mapping[str, Any]
    outcome_basis: OutcomeBasis
    readiness: EvaluationReadiness
    evaluated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        purpose: AssessmentPurpose,
        method: EvaluationMethod,
        compatibility_id: str,
        dataset_fingerprint: str,
        split_contract: str,
        population: Mapping[str, Any],
        exclusions: Mapping[str, Any],
        metrics: Mapping[str, Any],
        outcome_basis: OutcomeBasis,
        readiness: EvaluationReadiness,
        evaluated_at: datetime,
    ) -> LearningEvaluation:
        if _PURPOSE_METHOD[purpose] is not method:
            raise LearningContractError("purpose and evaluation method are incompatible")
        if (
            outcome_basis is OutcomeBasis.PRICE_PATH_ONLY
            and readiness is EvaluationReadiness.POLICY_REVIEW_ELIGIBLE
        ):
            raise LearningContractError(
                "PRICE_PATH_ONLY evaluation cannot be POLICY_REVIEW_ELIGIBLE"
            )
        for name, value in (
            ("compatibility_id", compatibility_id),
            ("dataset_fingerprint", dataset_fingerprint),
            ("split_contract", split_contract),
        ):
            _require_non_empty(name, value)
        contract_id = _EVALUATION_CONTRACT_BY_METHOD[method]
        identity = {
            "purpose": purpose,
            "method": method,
            "compatibility_id": compatibility_id,
            "dataset_fingerprint": dataset_fingerprint,
            "split_contract": split_contract,
            "population": population,
        }
        evaluation_id = stable_learning_id(contract_id, identity)
        draft = cls(
            evaluation_id=evaluation_id,
            artifact_digest="",
            schema_version=LEARNING_SCHEMA_VERSION,
            contract_id=contract_id,
            purpose=purpose,
            method=method,
            compatibility_id=compatibility_id,
            dataset_fingerprint=dataset_fingerprint,
            split_contract=split_contract,
            population=dict(population),
            exclusions=dict(exclusions),
            metrics=dict(metrics),
            outcome_basis=outcome_basis,
            readiness=readiness,
            evaluated_at=evaluated_at,
        )
        return cls(
            **{
                **asdict(draft),
                "artifact_digest": artifact_digest(
                    _artifact_payload(
                        draft, id_field="evaluation_id", digest_field="artifact_digest"
                    )
                ),
            }
        )


@dataclass(frozen=True)
class LearningPolicyProposal:
    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    proposal_id: str
    artifact_digest: str
    schema_version: int
    contract_id: LearningContractId
    source_evaluation_id: str
    current_config_hash: str
    changes: Mapping[str, Any]
    rationale: Mapping[str, Any]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        source_evaluation_id: str,
        current_config_hash: str,
        changes: Mapping[str, Any],
        rationale: Mapping[str, Any],
        created_at: datetime,
    ) -> LearningPolicyProposal:
        _require_non_empty("source_evaluation_id", source_evaluation_id)
        _require_non_empty("current_config_hash", current_config_hash)
        if not changes:
            raise LearningContractError("proposal changes must be non-empty")
        identity = {
            "source_evaluation_id": source_evaluation_id,
            "current_config_hash": current_config_hash,
            "changes": changes,
        }
        proposal_id = stable_learning_id(LearningContractId.SWING_PROPOSAL, identity)
        draft = cls(
            proposal_id=proposal_id,
            artifact_digest="",
            schema_version=LEARNING_SCHEMA_VERSION,
            contract_id=LearningContractId.SWING_PROPOSAL,
            source_evaluation_id=source_evaluation_id,
            current_config_hash=current_config_hash,
            changes=dict(changes),
            rationale=dict(rationale),
            created_at=created_at,
        )
        return cls(
            **{
                **asdict(draft),
                "artifact_digest": artifact_digest(
                    _artifact_payload(draft, id_field="proposal_id", digest_field="artifact_digest")
                ),
            }
        )


@dataclass(frozen=True)
class LearningPolicyValidation:
    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    validation_id: str
    artifact_digest: str
    schema_version: int
    contract_id: LearningContractId
    proposal_id: str
    baseline_evaluation_id: str
    proposed_evaluation_id: str
    population_fingerprint: str
    paired_deltas: Mapping[str, Any]
    issues: tuple[str, ...]
    status: ValidationStatus
    validated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        proposal_id: str,
        baseline_evaluation_id: str,
        proposed_evaluation_id: str,
        population_fingerprint: str,
        paired_deltas: Mapping[str, Any],
        issues: tuple[str, ...],
        status: ValidationStatus,
        validated_at: datetime,
    ) -> LearningPolicyValidation:
        for name, value in (
            ("proposal_id", proposal_id),
            ("baseline_evaluation_id", baseline_evaluation_id),
            ("proposed_evaluation_id", proposed_evaluation_id),
            ("population_fingerprint", population_fingerprint),
        ):
            _require_non_empty(name, value)
        required = {
            "net_return",
            "profit_factor",
            "average_return",
            "drawdown_regression",
            "trade_count",
            "regime_stability",
            "authority_coverage",
            "setup_readiness",
        }
        missing = sorted(required.difference(paired_deltas))
        if missing:
            raise LearningContractError(
                f"validation missing paired comparisons: {', '.join(missing)}"
            )
        if status is ValidationStatus.PASS and issues:
            raise LearningContractError("passing validation cannot have issues")
        if status is ValidationStatus.FAIL and not issues:
            raise LearningContractError("failed validation requires issues")
        identity = {
            "proposal_id": proposal_id,
            "baseline_evaluation_id": baseline_evaluation_id,
            "proposed_evaluation_id": proposed_evaluation_id,
            "population_fingerprint": population_fingerprint,
        }
        validation_id = stable_learning_id(LearningContractId.SWING_VALIDATION, identity)
        draft = cls(
            validation_id=validation_id,
            artifact_digest="",
            schema_version=LEARNING_SCHEMA_VERSION,
            contract_id=LearningContractId.SWING_VALIDATION,
            proposal_id=proposal_id,
            baseline_evaluation_id=baseline_evaluation_id,
            proposed_evaluation_id=proposed_evaluation_id,
            population_fingerprint=population_fingerprint,
            paired_deltas=dict(paired_deltas),
            issues=tuple(issues),
            status=status,
            validated_at=validated_at,
        )
        return cls(
            **{
                **asdict(draft),
                "artifact_digest": artifact_digest(
                    _artifact_payload(
                        draft, id_field="validation_id", digest_field="artifact_digest"
                    )
                ),
            }
        )


@dataclass(frozen=True)
class LearningPolicyApplication:
    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset()

    application_id: str
    artifact_digest: str
    schema_version: int
    contract_id: LearningContractId
    proposal_id: str
    validation_id: str
    previous_config_hash: str
    applied_config_hash: str
    exact_changes: Mapping[str, Any]
    confirmation_identity: str
    applied_at: datetime
    reread_verified: bool

    @classmethod
    def create(
        cls,
        *,
        proposal_id: str,
        validation_id: str,
        previous_config_hash: str,
        applied_config_hash: str,
        exact_changes: Mapping[str, Any],
        confirmation_identity: str,
        applied_at: datetime,
        reread_verified: bool,
    ) -> LearningPolicyApplication:
        for name, value in (
            ("proposal_id", proposal_id),
            ("validation_id", validation_id),
            ("previous_config_hash", previous_config_hash),
            ("applied_config_hash", applied_config_hash),
            ("confirmation_identity", confirmation_identity),
        ):
            _require_non_empty(name, value)
        if not exact_changes:
            raise LearningContractError("application exact_changes must be non-empty")
        if not reread_verified:
            raise LearningContractError("application requires reread verification")
        identity = {"proposal_id": proposal_id}
        application_id = stable_learning_id(LearningContractId.YAML_APPLICATION, identity)
        draft = cls(
            application_id=application_id,
            artifact_digest="",
            schema_version=LEARNING_SCHEMA_VERSION,
            contract_id=LearningContractId.YAML_APPLICATION,
            proposal_id=proposal_id,
            validation_id=validation_id,
            previous_config_hash=previous_config_hash,
            applied_config_hash=applied_config_hash,
            exact_changes=dict(exact_changes),
            confirmation_identity=confirmation_identity,
            applied_at=applied_at,
            reread_verified=reread_verified,
        )
        return cls(
            **{
                **asdict(draft),
                "artifact_digest": artifact_digest(
                    _artifact_payload(
                        draft, id_field="application_id", digest_field="artifact_digest"
                    )
                ),
            }
        )
