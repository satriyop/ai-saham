"""Pure schema-v1 contracts for database-owned learning artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Mapping

LEARNING_SCHEMA_VERSION = 1

# Option A population authority (typed binding on decision_payload). A 64-hex
# universe_id alone is never sufficient for challenge readiness.
ACCUM_POPULATION_AUTHORITY_CONTRACT = "population.accum.lq45_current_roster_pit_tradable.v1"
# Schema 2: attested membership_tickers / named_universe_tickers are required
# and membership must be a subset of the named roster.
ACCUM_POPULATION_BINDING_SCHEMA_VERSION = 2
# Schema 1: incomplete surface before attested ticker sets were required.
LEGACY_ACCUM_POPULATION_BINDING_SCHEMA_VERSION = 1
ACCUM_POPULATION_NAME = "lq45"
ACCUM_TRADABLE_MEMBERSHIP_CONTRACT = "pit_tradable.candle_presence.v1"
ACCUM_POPULATION_BENCHMARK_SYMBOL = "IHSG"
# Legacy shape-only contract retained for documentation of pre-schema-10 rows.
LEGACY_ACCUM_POPULATION_AUTHORITY_CONTRACT = "capture_universe_membership_digest.v1"
_UNIVERSE_MEMBERSHIP_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_MATERIAL_CONFIG_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ACCUM_POPULATION_BINDING_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "contract_id",
        "population_name",
        "membership_session",
        "membership_digest",
        "membership_count",
        "named_universe_digest",
        "tradable_membership_contract",
        "pit_tradable_lookback_sessions",
        "benchmark_symbol",
        "producer_source_revision",
        "membership_tickers",
        "named_universe_tickers",
    }
)


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
    # ADR-059: cohort-bound production policy identity for ML challenges.
    PRODUCTION_POLICY_SNAPSHOT_V1 = "production_policy_snapshot.v1"
    PRODUCTION_POLICY_SNAPSHOT_V2 = "production_policy_snapshot.v2"


# Closed accumulation export sets (ADR-059). Artifact contract and policy versions
# are separate: v2 gains a seventh policy_id while unchanged policies stay v1.
PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS = "screener.accum.score_weights"
PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS = "signal.accum.evidence_group_weights"
PRODUCTION_POLICY_ID_SIGNAL_FLAGS = "signal.accum.flags"
PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION = "signal.accum.classification"
PRODUCTION_POLICY_ID_RISK_HARD_GATES = "risk.accum.hard_gates"
PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE = "signal.accum.raw_score"
PRODUCTION_POLICY_ID_HARD_FILTERS = "screener.accum.hard_filters"

ACCUMULATION_PRODUCTION_POLICY_IDS_V1: tuple[str, ...] = (
    PRODUCTION_POLICY_ID_ACCUM_SCORE_WEIGHTS,
    PRODUCTION_POLICY_ID_SIGNAL_EVIDENCE_GROUPS,
    PRODUCTION_POLICY_ID_SIGNAL_FLAGS,
    PRODUCTION_POLICY_ID_SIGNAL_CLASSIFICATION,
    PRODUCTION_POLICY_ID_RISK_HARD_GATES,
    PRODUCTION_POLICY_ID_SIGNAL_RAW_SCORE,
)

ACCUMULATION_PRODUCTION_POLICY_IDS_V2: tuple[str, ...] = (
    *ACCUMULATION_PRODUCTION_POLICY_IDS_V1,
    PRODUCTION_POLICY_ID_HARD_FILTERS,
)

# Active producer closed set (v2 cutover).
ACCUMULATION_PRODUCTION_POLICY_IDS: tuple[str, ...] = ACCUMULATION_PRODUCTION_POLICY_IDS_V2

PRODUCTION_POLICY_VERSION_V1 = "v1"

_ALLOWED_PRODUCTION_POLICY_SNAPSHOT_CONTRACTS: frozenset[LearningContractId] = frozenset(
    {
        LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1,
        LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2,
    }
)


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


def stamp_universe_membership_id(tickers: Sequence[str]) -> str:
    """Stamp ACCUM observation ``universe_id`` from capture universe membership.

    Locked population authority for accumulation discovery observations:

    - **Contract:** ``capture_universe_membership_digest.v1``
    - **Form:** ``artifact_digest({"tickers": sorted(universe_tickers)})``
      as written by ``AccumulationCandidateObservationPersister``
    - **Operational universe policy:** LQ45 only for challenge corpus growth
      (recorded membership source is separate; historical index constituency
      warehouse remains parked)

    Free-form labels (``made-up-population``, ``lq45@pit``, etc.) are **not**
    population authority even when self-consistent with ``observation_id``.
    """

    return artifact_digest({"tickers": sorted(tickers)})


def is_accum_population_universe_id(universe_id: str) -> bool:
    """True when ``universe_id`` matches the locked ACCUM membership-digest stamp.

    Shape-only gate: 64 lowercase hex chars (sha256 of sorted ticker membership).
    Does not reconstruct historical LQ45 constituency (parked warehouse).
    **Not** population authority for readiness — require typed AccumPopulationBinding.
    """

    if not isinstance(universe_id, str):
        return False
    return _UNIVERSE_MEMBERSHIP_DIGEST_RE.fullmatch(universe_id) is not None


def _normalize_ticker_set(tickers: Sequence[str] | Any, *, field: str) -> tuple[str, ...]:
    """Sort/unique/uppercase ticker set; empty after normalize is a contract error."""
    if not isinstance(tickers, Sequence) or isinstance(tickers, (str, bytes)):
        raise LearningContractError(
            f"population_binding.{field} must be a non-empty ticker sequence"
        )
    normalized = tuple(sorted({str(t).strip().upper() for t in tickers if str(t).strip()}))
    if not normalized:
        raise LearningContractError(f"population_binding.{field} must be non-empty")
    return normalized


@dataclass(frozen=True)
class AccumPopulationBinding:
    """Typed producer-attested population binding (Option A, schema-10 payload).

    Population meaning: current configured LQ45 roster intersected with
    candle-active PIT tradability for the observation session. Not historical
    LQ45 index constituency reconstruction.

    Attested ticker sets are part of the authority surface so readiness can
    recompute membership_count / membership_digest / named_universe_digest
    without live config I/O. Shape-only digests and counts are never sufficient.
    """

    schema_version: int
    contract_id: str
    population_name: str
    membership_session: str
    membership_digest: str
    membership_count: int
    named_universe_digest: str
    tradable_membership_contract: str
    pit_tradable_lookback_sessions: int
    benchmark_symbol: str
    producer_source_revision: str
    membership_tickers: tuple[str, ...]
    named_universe_tickers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "population_name": self.population_name,
            "membership_session": self.membership_session,
            "membership_digest": self.membership_digest,
            "membership_count": self.membership_count,
            "named_universe_digest": self.named_universe_digest,
            "tradable_membership_contract": self.tradable_membership_contract,
            "pit_tradable_lookback_sessions": self.pit_tradable_lookback_sessions,
            "benchmark_symbol": self.benchmark_symbol,
            "producer_source_revision": self.producer_source_revision,
            "membership_tickers": list(self.membership_tickers),
            "named_universe_tickers": list(self.named_universe_tickers),
        }

    @classmethod
    def create(
        cls,
        *,
        membership_tickers: Sequence[str],
        named_universe_tickers: Sequence[str],
        membership_session: date | str,
        pit_tradable_lookback_sessions: int,
        producer_source_revision: str,
        population_name: str = ACCUM_POPULATION_NAME,
        benchmark_symbol: str = ACCUM_POPULATION_BENCHMARK_SYMBOL,
        tradable_membership_contract: str = ACCUM_TRADABLE_MEMBERSHIP_CONTRACT,
    ) -> AccumPopulationBinding:
        """Build a complete current-schema binding from capture-time membership inputs."""
        from datetime import date as date_cls

        if isinstance(membership_session, date_cls):
            session_s = membership_session.isoformat()
        else:
            session_s = str(membership_session).strip()
        if not session_s:
            raise LearningContractError("membership_session must be non-empty")
        if pit_tradable_lookback_sessions < 1:
            raise LearningContractError(
                f"pit_tradable_lookback_sessions must be >= 1, got {pit_tradable_lookback_sessions}"
            )
        _require_non_empty("producer_source_revision", producer_source_revision)
        _require_non_empty("population_name", population_name)
        _require_non_empty("benchmark_symbol", benchmark_symbol)
        _require_non_empty("tradable_membership_contract", tradable_membership_contract)
        # Production write authority is locked to the challenge-corpus population.
        # Unsupported names (e.g. idx30) must fail before schema-10 persist — not
        # only later at readiness. from_mapping remains permissive for read-side
        # historical/adversarial rows.
        if population_name != ACCUM_POPULATION_NAME:
            raise LearningContractError(
                f"unsupported population_name={population_name!r}; "
                f"challenge-corpus production binding requires "
                f"population_name={ACCUM_POPULATION_NAME!r} "
                f"(contract={ACCUM_POPULATION_AUTHORITY_CONTRACT})"
            )
        membership = _normalize_ticker_set(membership_tickers, field="membership_tickers")
        named = _normalize_ticker_set(named_universe_tickers, field="named_universe_tickers")
        # Population meaning: configured named roster ∩ PIT-tradable membership.
        # Membership must be a subset of the named universe (never invent tickers).
        named_set = set(named)
        extras = tuple(t for t in membership if t not in named_set)
        if extras:
            raise LearningContractError(
                "membership_tickers must be a subset of named_universe_tickers "
                f"(extra={list(extras)!r})"
            )
        membership_digest = stamp_universe_membership_id(membership)
        named_digest = stamp_universe_membership_id(named)
        return cls(
            schema_version=ACCUM_POPULATION_BINDING_SCHEMA_VERSION,
            contract_id=ACCUM_POPULATION_AUTHORITY_CONTRACT,
            population_name=population_name,
            membership_session=session_s,
            membership_digest=membership_digest,
            membership_count=len(membership),
            named_universe_digest=named_digest,
            tradable_membership_contract=tradable_membership_contract,
            pit_tradable_lookback_sessions=int(pit_tradable_lookback_sessions),
            benchmark_symbol=benchmark_symbol,
            producer_source_revision=producer_source_revision.strip(),
            membership_tickers=membership,
            named_universe_tickers=named,
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> AccumPopulationBinding:
        """Parse stored binding without normalizing authority fields.

        Read-side authority: preserve exact persisted types and string forms.
        Producer ``create()`` may normalize; this path must not coerce strings
        to ints, strip whitespace, uppercase tickers, or re-sort arrays before
        validation can see the original corruption.
        """
        if not isinstance(raw, Mapping):
            raise LearningContractError(
                f"population_binding must be a mapping, got {type(raw).__name__}"
            )
        keys = frozenset(raw.keys())
        if keys != _ACCUM_POPULATION_BINDING_KEYS:
            missing = sorted(_ACCUM_POPULATION_BINDING_KEYS - keys)
            extra = sorted(keys - _ACCUM_POPULATION_BINDING_KEYS)
            raise LearningContractError(
                f"population_binding key set mismatch missing={missing!r} extra={extra!r}"
            )

        def _exact_int(field: str) -> int:
            value = raw[field]
            if type(value) is not int:
                raise LearningContractError(
                    f"population_binding.{field} must be exact int, "
                    f"got {type(value).__name__}={value!r}"
                )
            return value

        def _exact_str(field: str) -> str:
            value = raw[field]
            if type(value) is not str:
                raise LearningContractError(
                    f"population_binding.{field} must be exact str, "
                    f"got {type(value).__name__}={value!r}"
                )
            if value != value.strip() or not value:
                raise LearningContractError(
                    f"population_binding.{field} must be non-empty without "
                    f"surrounding whitespace, got {value!r}"
                )
            return value

        def _exact_tickers(field: str) -> tuple[str, ...]:
            value = raw[field]
            if not isinstance(value, list):
                raise LearningContractError(
                    f"population_binding.{field} must be a JSON array of strings"
                )
            out: list[str] = []
            for i, item in enumerate(value):
                if type(item) is not str:
                    raise LearningContractError(
                        f"population_binding.{field}[{i}] must be str, "
                        f"got {type(item).__name__}={item!r}"
                    )
                if not item or item != item.strip():
                    raise LearningContractError(
                        f"population_binding.{field}[{i}] must be non-empty "
                        f"without surrounding whitespace, got {item!r}"
                    )
                out.append(item)
            if not out:
                raise LearningContractError(f"population_binding.{field} must be non-empty")
            return tuple(out)

        return cls(
            schema_version=_exact_int("schema_version"),
            contract_id=_exact_str("contract_id"),
            population_name=_exact_str("population_name"),
            membership_session=_exact_str("membership_session"),
            membership_digest=_exact_str("membership_digest"),
            membership_count=_exact_int("membership_count"),
            named_universe_digest=_exact_str("named_universe_digest"),
            tradable_membership_contract=_exact_str("tradable_membership_contract"),
            pit_tradable_lookback_sessions=_exact_int("pit_tradable_lookback_sessions"),
            benchmark_symbol=_exact_str("benchmark_symbol"),
            producer_source_revision=_exact_str("producer_source_revision"),
            membership_tickers=_exact_tickers("membership_tickers"),
            named_universe_tickers=_exact_tickers("named_universe_tickers"),
        )


def validate_accum_population_binding(
    binding: AccumPopulationBinding,
    *,
    outer_universe_id: str,
    economic_session: date | str | None,
) -> None:
    """Fail-closed validation of every exact Option A field and cross-link.

    Recomputes membership_count, membership_digest, and named_universe_digest
    from the attested ticker sets. Positive count and hash shape alone never
    grant authority.
    """
    from datetime import date as date_cls

    if binding.schema_version != ACCUM_POPULATION_BINDING_SCHEMA_VERSION:
        raise LearningContractError(
            f"population_binding.schema_version={binding.schema_version}"
            f"!=expected:{ACCUM_POPULATION_BINDING_SCHEMA_VERSION}"
        )
    if binding.contract_id != ACCUM_POPULATION_AUTHORITY_CONTRACT:
        raise LearningContractError(
            f"population_binding.contract_id={binding.contract_id!r}"
            f"!=expected:{ACCUM_POPULATION_AUTHORITY_CONTRACT!r}"
        )
    if binding.population_name != ACCUM_POPULATION_NAME:
        raise LearningContractError(
            f"population_binding.population_name={binding.population_name!r}"
            f"!=expected:{ACCUM_POPULATION_NAME!r}"
        )
    if binding.tradable_membership_contract != ACCUM_TRADABLE_MEMBERSHIP_CONTRACT:
        raise LearningContractError(
            "population_binding.tradable_membership_contract="
            f"{binding.tradable_membership_contract!r}"
            f"!=expected:{ACCUM_TRADABLE_MEMBERSHIP_CONTRACT!r}"
        )
    if binding.benchmark_symbol != ACCUM_POPULATION_BENCHMARK_SYMBOL:
        raise LearningContractError(
            f"population_binding.benchmark_symbol={binding.benchmark_symbol!r}"
            f"!=expected:{ACCUM_POPULATION_BENCHMARK_SYMBOL!r}"
        )
    if binding.pit_tradable_lookback_sessions < 1:
        raise LearningContractError(
            "population_binding.pit_tradable_lookback_sessions must be >= 1, "
            f"got {binding.pit_tradable_lookback_sessions}"
        )
    if not binding.producer_source_revision.strip():
        raise LearningContractError("population_binding.producer_source_revision must be non-empty")

    membership = _normalize_ticker_set(binding.membership_tickers, field="membership_tickers")
    named = _normalize_ticker_set(binding.named_universe_tickers, field="named_universe_tickers")
    # Canonical order is part of the stamp surface; reject unsorted/duplicate
    # attestations that would otherwise re-normalize into a matching digest.
    if tuple(binding.membership_tickers) != membership:
        raise LearningContractError(
            "population_binding.membership_tickers must be sorted unique uppercase"
        )
    if tuple(binding.named_universe_tickers) != named:
        raise LearningContractError(
            "population_binding.named_universe_tickers must be sorted unique uppercase"
        )
    # Declared population meaning: named LQ45 roster ∩ PIT-tradable membership.
    # Digests/counts alone never authorize a membership ticker outside the named roster.
    named_set = set(named)
    extras = tuple(t for t in membership if t not in named_set)
    if extras:
        raise LearningContractError(
            "population_binding.membership_tickers must be a subset of "
            "named_universe_tickers "
            f"(extra={list(extras)!r})"
        )

    expected_count = len(membership)
    if binding.membership_count != expected_count:
        raise LearningContractError(
            "population_binding.membership_count does not match attested membership "
            f"(count={binding.membership_count}, expected={expected_count})"
        )
    expected_membership_digest = stamp_universe_membership_id(membership)
    if binding.membership_digest != expected_membership_digest:
        raise LearningContractError(
            "population_binding.membership_digest does not match attested membership_tickers "
            f"(binding={binding.membership_digest!r}, "
            f"recomputed={expected_membership_digest!r})"
        )
    expected_named_digest = stamp_universe_membership_id(named)
    if binding.named_universe_digest != expected_named_digest:
        raise LearningContractError(
            "population_binding.named_universe_digest does not match "
            "attested named_universe_tickers "
            f"(binding={binding.named_universe_digest!r}, "
            f"recomputed={expected_named_digest!r})"
        )
    if not is_accum_population_universe_id(binding.membership_digest):
        raise LearningContractError(
            f"population_binding.membership_digest shape invalid: {binding.membership_digest!r}"
        )
    if not is_accum_population_universe_id(binding.named_universe_digest):
        raise LearningContractError(
            "population_binding.named_universe_digest shape invalid: "
            f"{binding.named_universe_digest!r}"
        )
    if binding.membership_digest != outer_universe_id:
        raise LearningContractError(
            "population_binding.membership_digest must equal outer universe_id "
            f"(binding={binding.membership_digest!r}, universe_id={outer_universe_id!r})"
        )
    session_raw = economic_session
    if isinstance(session_raw, date_cls):
        session_s = session_raw.isoformat()
    elif isinstance(session_raw, str):
        session_s = session_raw.strip()
    else:
        session_s = ""
    if not session_s:
        raise LearningContractError(
            "population_binding requires a bound economic session for membership_session link"
        )
    if binding.membership_session != session_s:
        raise LearningContractError(
            "population_binding.membership_session must equal economic session "
            f"(binding={binding.membership_session!r}, session={session_s!r})"
        )


def recompute_path_label_fingerprint(
    *,
    observation_id: str,
    observation_artifact_digest: str,
    label_contract: LearningContractId | str,
) -> str:
    """Producer fingerprint: digest(observation_id, decision_digest, label_contract)."""
    contract_value = (
        label_contract.value
        if isinstance(label_contract, LearningContractId)
        else str(label_contract)
    )
    return artifact_digest(
        {
            "observation_id": observation_id,
            "decision_digest": observation_artifact_digest,
            "label_contract": contract_value,
        }
    )


def _require_non_empty(name: str, value: Any) -> None:
    """Require a non-empty exact str (type-checked before strip-based emptiness)."""
    if type(value) is not str:
        raise LearningContractError(
            f"{name} must be exact str, got {type(value).__name__}={value!r}"
        )
    if not value:
        raise LearningContractError(f"{name} must be non-empty")
    if value != value.strip():
        raise LearningContractError(f"{name} must not have surrounding whitespace (got {value!r})")


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
    # ADR-068 §6: producer_source_revision is provenance beside identity.
    # It must not participate in observation_id or artifact_digest so a
    # re-capture under a different build of the same measured behaviour is
    # still the same immutable content. captured_at still participates in the
    # digest (deliberate; see repository tests for the production first-write
    # pre-existence guard that protects re-backfill).
    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset({"producer_source_revision"})

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
    producer_source_revision: str

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
        producer_source_revision: str,
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
            ("producer_source_revision", producer_source_revision),
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
            producer_source_revision=producer_source_revision.strip(),
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


def validate_label_availability_outcome(
    availability: LabelAvailability,
    outcome: str | None,
) -> None:
    """Enforce availability↔outcome invariant (create and read/reopen gates).

    - ``AVAILABLE`` requires a non-``None`` outcome
    - ``UNAVAILABLE`` must not carry an outcome

    Creation-time checks alone are insufficient: readiness must revalidate after
    load/reconstruction so a rehashed AVAILABLE+None label cannot count as H10.
    """

    if availability is LabelAvailability.AVAILABLE and outcome is None:
        raise LearningContractError("available label requires an outcome")
    if availability is LabelAvailability.UNAVAILABLE and outcome is not None:
        raise LearningContractError("unavailable label cannot carry an outcome")


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
        validate_label_availability_outcome(availability, outcome)
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


def recompute_observation_id(observation: LearningObservation) -> str:
    """Recompute observation_id from its seven relational identity dimensions."""

    identity = {
        "purpose": observation.purpose,
        "policy_contract": observation.policy_contract,
        "horizon_contract": observation.horizon_contract,
        "compatibility_id": observation.compatibility_id,
        "cutoff_at": observation.cutoff_at,
        "universe_id": observation.universe_id,
        "window_id": observation.window_id,
    }
    return stable_learning_id(observation.contract_id, identity)


def validate_observation_identity(observation: LearningObservation) -> None:
    """Reject an observation whose id does not match its typed identity."""

    expected = recompute_observation_id(observation)
    if observation.observation_id != expected:
        raise LearningContractError(
            "observation_id does not match recomputed identity "
            f"(stored={observation.observation_id!r}, expected={expected!r})"
        )


def recompute_label_id(label: LearningOutcomeLabel) -> str:
    """Recompute label_id from (observation_id, contract_id)."""

    identity = {
        "observation_id": label.observation_id,
        "contract_id": label.contract_id,
    }
    return stable_learning_id(label.contract_id, identity)


def validate_label_identity(label: LearningOutcomeLabel) -> None:
    """Reject a label whose id does not match its typed identity."""

    expected = recompute_label_id(label)
    if label.label_id != expected:
        raise LearningContractError(
            "label_id does not match recomputed identity "
            f"(stored={label.label_id!r}, expected={expected!r})"
        )


def modern_label_digest(label: LearningOutcomeLabel) -> str:
    """Digest under the current contract (``labeled_at`` excluded)."""

    return artifact_digest(
        _artifact_payload(label, id_field="label_id", digest_field="artifact_digest")
    )


def legacy_labeled_at_label_digest(label: LearningOutcomeLabel) -> str:
    """Digest under the pre-11bfca95 rule that hashed wall-clock ``labeled_at``.

    Used only to classify rows written before label digests excluded
    ``labeled_at`` so they can be rehashed without guessing other corruption.
    """

    payload = asdict(label)
    payload.pop("label_id")
    payload.pop("artifact_digest")
    return artifact_digest(payload)


def label_has_legacy_labeled_at_digest(label: LearningOutcomeLabel) -> bool:
    """True when stored digest matches the legacy-with-labeled_at formula only."""

    stored = label.artifact_digest
    if stored == modern_label_digest(label):
        return False
    return stored == legacy_labeled_at_label_digest(label)


def rehash_label_excluding_labeled_at(label: LearningOutcomeLabel) -> LearningOutcomeLabel:
    """Return the same label content with a modern digest (``labeled_at`` out).

    - Already modern → returned unchanged.
    - Legacy (digest included ``labeled_at``) → new digest, same outcomes/metrics.
    - Any other mismatch → contract error (do not silently rewrite unknown corruption).
    """

    modern = modern_label_digest(label)
    if label.artifact_digest == modern:
        return label
    if label.artifact_digest != legacy_labeled_at_label_digest(label):
        raise LearningContractError(
            "label digest matches neither modern nor legacy labeled_at rules; "
            f"refusing rehash for label_id={label.label_id!r}"
        )
    return LearningOutcomeLabel(
        label_id=label.label_id,
        artifact_digest=modern,
        schema_version=label.schema_version,
        contract_id=label.contract_id,
        observation_id=label.observation_id,
        outcome_basis=label.outcome_basis,
        availability=label.availability,
        outcome=label.outcome,
        metrics=dict(label.metrics),
        fingerprint=label.fingerprint,
        labeled_at=label.labeled_at,
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


# ADR-068 removed ``material_config_hash_from_canonical``. It hashed the raw
# resolved-config bytes for the policy-snapshot ``material_config_hash`` column,
# and was the domain half of the deleted config-byte identity mechanism. That
# column now carries the ADR-059 seven-row payload fold, which is also the
# declared-policy axis of the cohort id, so the two can never disagree — see
# ``src/application/services/behavioral_cohort_identity.py``. Keeping this
# function would leave a usable path back to config-byte identity, which
# ADR-068 §7 forbids.


def policy_snapshot_payload_digest(canonical_payload: Mapping[str, Any]) -> str:
    """SHA-256 of canonical payload JSON (lowercase hex, no prefix)."""

    return hashlib.sha256(canonical_json(canonical_payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProductionPolicySnapshot:
    """Cohort-bound production policy identity (ADR-059).

    ``payload_digest`` covers only ``canonical_payload``. ``created_at`` and
    ``source_revision`` are provenance and must not affect identity or digest.
    """

    DIGEST_EXCLUDED_FIELDS: ClassVar[frozenset[str]] = frozenset({"created_at", "source_revision"})

    snapshot_id: str
    schema_version: int
    contract_id: LearningContractId
    purpose: AssessmentPurpose
    learning_observation_contract_id: str
    producer_observation_contract: str
    compatibility_id: str
    policy_id: str
    policy_version: str
    decision_type: str
    semantic_engine_contract_id: str
    material_config_hash: str
    canonical_payload: Mapping[str, Any]
    payload_digest: str
    source_revision: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        contract_id: LearningContractId,
        purpose: AssessmentPurpose,
        learning_observation_contract_id: str,
        producer_observation_contract: str,
        compatibility_id: str,
        policy_id: str,
        policy_version: str,
        decision_type: str,
        semantic_engine_contract_id: str,
        material_config_hash: str,
        canonical_payload: Mapping[str, Any],
        source_revision: str,
        created_at: datetime,
    ) -> ProductionPolicySnapshot:
        if not isinstance(contract_id, LearningContractId):
            raise LearningContractError(
                f"contract_id must be a LearningContractId, got {type(contract_id).__name__}"
            )
        if contract_id not in _ALLOWED_PRODUCTION_POLICY_SNAPSHOT_CONTRACTS:
            raise LearningContractError(
                "contract_id must be production_policy_snapshot.v1 or "
                f"production_policy_snapshot.v2, got {contract_id!r}"
            )
        for name, value in (
            ("learning_observation_contract_id", learning_observation_contract_id),
            ("producer_observation_contract", producer_observation_contract),
            ("compatibility_id", compatibility_id),
            ("policy_id", policy_id),
            ("policy_version", policy_version),
            ("decision_type", decision_type),
            ("semantic_engine_contract_id", semantic_engine_contract_id),
            ("material_config_hash", material_config_hash),
            ("source_revision", source_revision),
        ):
            _require_non_empty(name, value)
        if _MATERIAL_CONFIG_HASH_RE.fullmatch(material_config_hash) is None:
            raise LearningContractError(
                "material_config_hash must match ^sha256:[0-9a-f]{64}$, "
                f"got {material_config_hash!r}"
            )
        if not isinstance(canonical_payload, Mapping) or not canonical_payload:
            raise LearningContractError("canonical_payload must be a non-empty mapping")
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise LearningContractError("created_at must be timezone-aware")

        payload = dict(canonical_payload)
        _assert_payload_column_metadata_match(
            payload,
            policy_id=policy_id,
            policy_version=policy_version,
            decision_type=decision_type,
            semantic_engine_contract_id=semantic_engine_contract_id,
        )

        identity = {
            "purpose": purpose,
            "learning_observation_contract_id": learning_observation_contract_id,
            "producer_observation_contract": producer_observation_contract,
            "compatibility_id": compatibility_id,
            "policy_id": policy_id,
        }
        snapshot_id = stable_learning_id(contract_id, identity)
        digest = policy_snapshot_payload_digest(payload)
        return cls(
            snapshot_id=snapshot_id,
            schema_version=LEARNING_SCHEMA_VERSION,
            contract_id=contract_id,
            purpose=purpose,
            learning_observation_contract_id=learning_observation_contract_id,
            producer_observation_contract=producer_observation_contract,
            compatibility_id=compatibility_id,
            policy_id=policy_id,
            policy_version=policy_version,
            decision_type=decision_type,
            semantic_engine_contract_id=semantic_engine_contract_id,
            material_config_hash=material_config_hash,
            canonical_payload=payload,
            payload_digest=digest,
            source_revision=source_revision,
            created_at=created_at,
        )


_PAYLOAD_COLUMN_METADATA_KEYS: tuple[str, ...] = (
    "policy_id",
    "policy_version",
    "decision_type",
    "semantic_engine_contract_id",
)


def _assert_payload_column_metadata_match(
    payload: Mapping[str, Any],
    *,
    policy_id: str,
    policy_version: str,
    decision_type: str,
    semantic_engine_contract_id: str,
) -> None:
    """Fail closed when duplicated payload metadata drifts from row columns."""

    expected = {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "decision_type": decision_type,
        "semantic_engine_contract_id": semantic_engine_contract_id,
    }
    for key, column_value in expected.items():
        if key not in payload:
            raise LearningContractError(
                f"policy snapshot payload missing required metadata key {key!r}"
            )
        if payload[key] != column_value:
            raise LearningContractError(
                f"policy snapshot payload {key!r}={payload[key]!r} does not match "
                f"column value {column_value!r}"
            )


def validate_policy_snapshot_integrity(snapshot: ProductionPolicySnapshot) -> None:
    """Reject a snapshot whose id, digest, or column/payload metadata disagree."""

    if snapshot.contract_id not in _ALLOWED_PRODUCTION_POLICY_SNAPSHOT_CONTRACTS:
        raise LearningContractError("policy snapshot contract_id mismatch")
    if type(snapshot.source_revision) is not str or not snapshot.source_revision:
        raise LearningContractError("source_revision must be non-empty provenance")
    if snapshot.source_revision != snapshot.source_revision.strip():
        raise LearningContractError(
            "source_revision must not have surrounding whitespace "
            f"(got {snapshot.source_revision!r})"
        )
    if type(snapshot.material_config_hash) is not str or (
        _MATERIAL_CONFIG_HASH_RE.fullmatch(snapshot.material_config_hash) is None
    ):
        raise LearningContractError(
            "material_config_hash must match ^sha256:[0-9a-f]{64}$, "
            f"got {snapshot.material_config_hash!r}"
        )
    if snapshot.created_at.tzinfo is None or snapshot.created_at.utcoffset() is None:
        raise LearningContractError("created_at must be timezone-aware")
    expected_id = stable_learning_id(
        snapshot.contract_id,
        {
            "purpose": snapshot.purpose,
            "learning_observation_contract_id": snapshot.learning_observation_contract_id,
            "producer_observation_contract": snapshot.producer_observation_contract,
            "compatibility_id": snapshot.compatibility_id,
            "policy_id": snapshot.policy_id,
        },
    )
    if snapshot.snapshot_id != expected_id:
        raise LearningContractError("policy snapshot_id does not match its identity")
    expected_digest = policy_snapshot_payload_digest(snapshot.canonical_payload)
    if snapshot.payload_digest != expected_digest:
        raise LearningContractError("policy snapshot payload_digest does not match payload")
    _assert_payload_column_metadata_match(
        snapshot.canonical_payload,
        policy_id=snapshot.policy_id,
        policy_version=snapshot.policy_version,
        decision_type=snapshot.decision_type,
        semantic_engine_contract_id=snapshot.semantic_engine_contract_id,
    )
