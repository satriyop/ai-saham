"""Pure producer readiness projection for accumulation challenge corpus (P0).

Layer: Application (pure). No I/O. Classifies each explicit compatibility cohort
using locked rules from grow_snapshot_bound_accum_challenge_corpus.md.

Producer status is a handoff gate, not an ML fold/verdict.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Mapping, Sequence

from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2,
)
from src.application.services.lean_observation_identity import (
    POLICY_SNAPSHOT_BINDING_CONTRACT_V2,
)
from src.domain.value_objects.learning_artifacts import (
    ACCUM_POPULATION_AUTHORITY_CONTRACT,
    ACCUMULATION_PRODUCTION_POLICY_IDS_V1,
    ACCUMULATION_PRODUCTION_POLICY_IDS_V2,
    LEARNING_SCHEMA_VERSION,
    PRODUCTION_POLICY_VERSION_V1,
    AssessmentPurpose,
    LabelAvailability,
    LearningContractError,
    LearningContractId,
    LearningObservation,
    LearningOutcomeLabel,
    OutcomeBasis,
    ProductionPolicySnapshot,
    is_accum_population_universe_id,
    validate_artifact_integrity,
    validate_label_availability_outcome,
    validate_label_identity,
    validate_observation_identity,
    validate_policy_snapshot_integrity,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_HORIZON_CONTRACT,
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
    ACCUMULATION_DISCOVERY_POLICY_CONTRACT,
)

# Exact economic session date (ADR-056 payload). No prefix/slice acceptance.
_SESSION_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Production window_id: {TICKER}:{YYYY-MM-DD} (ADR-056; no window length in identity).
_WINDOW_ID_RE = re.compile(r"^([A-Z0-9.\-]+):(\d{4}-\d{2}-\d{2})$")
ACTIVE_SESSION_ARTIFACT_TYPE = "accumulation_session_observation"
# Production session payload locks from build_session_observation_payload.
ACTIVE_SESSION_WORKFLOW = "research_accum_capture"
ACTIVE_SESSION_HORIZON_PRIMARY = "accum_10d"
ACTIVE_CANONICAL_WINDOW = 7
ACTIVE_FEATURES_WINDOWS: frozenset[str] = frozenset({"7", "30", "90"})
ACTIVE_OUTER_SCHEMA_VERSION = LEARNING_SCHEMA_VERSION
ACTIVE_PAYLOAD_SCHEMA_VERSION = CANDIDATE_OBSERVATION_SCHEMA_VERSION

# Active closed set for production-baseline challenges (ADR-059 v2).
ACTIVE_SNAPSHOT_BINDING_CONTRACT = POLICY_SNAPSHOT_BINDING_CONTRACT_V2
ACTIVE_REQUIRED_POLICY_IDS: tuple[str, ...] = ACCUMULATION_PRODUCTION_POLICY_IDS_V2
ACTIVE_LEARNING_OBSERVATION_CONTRACT = LearningContractId.ACCUMULATION_OBSERVATION.value
ACTIVE_PRODUCER_OBSERVATION_CONTRACT = ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT
ACTIVE_POLICY_CONTRACT = ACCUMULATION_DISCOVERY_POLICY_CONTRACT
ACTIVE_HORIZON_CONTRACT = ACCUMULATION_DISCOVERY_HORIZON_CONTRACT
ACTIVE_LABEL_OUTCOME_BASIS = OutcomeBasis.PRICE_PATH_ONLY
PRIMARY_LABEL_CONTRACT = LearningContractId.ACCUM_10D_LABEL
PATH_LABEL_CONTRACTS: tuple[LearningContractId, ...] = (
    LearningContractId.ACCUM_3D_LABEL,
    LearningContractId.ACCUM_10D_LABEL,
    LearningContractId.ACCUM_20D_LABEL,
)
# Population authority for ACCUM challenge inputs (locked choice c — write-path
# membership digest). Free-form universe_id strings are not population authority.
ACTIVE_POPULATION_AUTHORITY_CONTRACT = ACCUM_POPULATION_AUTHORITY_CONTRACT

# Horizon nicknames for operator-facing reports (H3/H10/H20).
_HORIZON_KEY_BY_CONTRACT: Mapping[LearningContractId, str] = {
    LearningContractId.ACCUM_3D_LABEL: "H3",
    LearningContractId.ACCUM_10D_LABEL: "H10",
    LearningContractId.ACCUM_20D_LABEL: "H20",
}


class ProducerReadinessStatus(str, Enum):
    """Exact producer classification for one compatibility cohort."""

    LEGACY_RAW_ONLY = "LEGACY_RAW_ONLY"
    BLOCKED_POLICY = "BLOCKED_POLICY"
    COLLECTING = "COLLECTING"
    CHALLENGE_INPUT_READY = "CHALLENGE_INPUT_READY"


@dataclass(frozen=True)
class SnapshotBindingReport:
    """Verified closed-set status for one cohort's policy snapshots."""

    binding_contract: str
    required_policy_ids: tuple[str, ...]
    required_count: int
    verified_count: int
    verified_policy_ids: tuple[str, ...]
    missing_policy_ids: tuple[str, ...]
    extra_policy_ids: tuple[str, ...]
    invalid_policy_ids: tuple[str, ...]
    observed_contract_ids: tuple[str, ...]
    material_config_hashes: tuple[str, ...]
    active_set_verified: bool
    has_corruption: bool
    claims_active_binding: bool


@dataclass(frozen=True)
class ObservationCohortValidation:
    """Result of validating every observation against the accum contract."""

    expected_learning_observation_contract_id: str
    expected_producer_observation_contract: str
    valid_observation_count: int
    invalid_observation_count: int
    invalid_reasons: tuple[str, ...]
    session_dates: tuple[date, ...]
    has_contract_corruption: bool


@dataclass(frozen=True)
class LabelHorizonCounts:
    """Per-horizon label states for one cohort."""

    available: int
    unavailable: int
    insufficient_horizon: int
    conflict: int


@dataclass(frozen=True)
class LabelCohortValidation:
    """Label integrity + horizon counts for one cohort."""

    counts_by_horizon: Mapping[str, LabelHorizonCounts]
    invalid_label_count: int
    invalid_reasons: tuple[str, ...]
    has_integrity_corruption: bool


@dataclass(frozen=True)
class CohortProducerReadiness:
    """Read-only readiness projection for one compatibility cohort."""

    compatibility_id: str
    observation_contract: str
    observation_count: int
    session_count: int
    economic_date_min: str | None
    economic_date_max: str | None
    snapshot: SnapshotBindingReport
    observation_validation: ObservationCohortValidation
    label_validation: LabelCohortValidation
    labels_by_horizon: Mapping[str, LabelHorizonCounts]
    action_distribution: Mapping[str, int]
    setup_readiness_present: int
    setup_readiness_missing: int
    setup_readiness_state_distribution: Mapping[str, int]
    producer_status: ProducerReadinessStatus


def classify_producer_status(
    *,
    snapshot: SnapshotBindingReport,
    observation_validation: ObservationCohortValidation,
    label_validation: LabelCohortValidation,
    session_count: int,
    available_h10_labels: int,
) -> ProducerReadinessStatus:
    """Apply locked precedence rules for one cohort.

    Rules (exact):
    - LEGACY_RAW_ONLY: observations exist under absent/unknown/historical binding
      without snapshot corruption and without observation/label corruption.
    - BLOCKED_POLICY: active binding claimed but set partial/mixed/malformed/
      invalid/mismatched, any snapshot corruption, observation contract/
      provenance/digest corruption, or label digest corruption.
    - COLLECTING: exact active snapshots verify, observations+labels validate,
      but <2 sessions or zero AVAILABLE primary H10 labels.
    - CHALLENGE_INPUT_READY: exact active snapshots verify, observations+labels
      validate, ≥2 sessions, and ≥1 AVAILABLE price_path.accum_10d.v1 label.
    """
    if (
        snapshot.has_corruption
        or observation_validation.has_contract_corruption
        or label_validation.has_integrity_corruption
        or (snapshot.claims_active_binding and not snapshot.active_set_verified)
    ):
        return ProducerReadinessStatus.BLOCKED_POLICY
    if not snapshot.active_set_verified:
        return ProducerReadinessStatus.LEGACY_RAW_ONLY
    if session_count < 2 or available_h10_labels < 1:
        return ProducerReadinessStatus.COLLECTING
    return ProducerReadinessStatus.CHALLENGE_INPUT_READY


def _snapshot_matches_production_descriptor(snap: ProductionPolicySnapshot) -> bool:
    """True when row columns match the authoritative production descriptor map."""
    descriptor = ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2.get(snap.policy_id)
    if descriptor is None:
        return False
    if snap.decision_type != descriptor.decision_type:
        return False
    if snap.semantic_engine_contract_id != descriptor.semantic_engine_contract_id:
        return False
    if snap.policy_version != descriptor.policy_version:
        return False
    # Payload metadata must match columns (already integrity-checked) and descriptor.
    payload = snap.canonical_payload
    if not isinstance(payload, Mapping):
        return False
    if payload.get("decision_type") != descriptor.decision_type:
        return False
    if payload.get("semantic_engine_contract_id") != descriptor.semantic_engine_contract_id:
        return False
    if payload.get("policy_version") != descriptor.policy_version:
        return False
    if payload.get("policy_id") != snap.policy_id:
        return False
    return True


def verify_snapshot_binding(
    snapshots: Sequence[ProductionPolicySnapshot],
    *,
    purpose_value: str,
    compatibility_id: str,
    expected_learning_observation_contract_id: str = ACTIVE_LEARNING_OBSERVATION_CONTRACT,
    expected_producer_observation_contract: str = ACTIVE_PRODUCER_OBSERVATION_CONTRACT,
) -> SnapshotBindingReport:
    """Verify snapshots for a cohort against the active v2 closed set.

    Enforces row integrity, purpose/compat/observation contracts, authoritative
    production descriptors (decision_type, semantic contract, policy version),
    and a single shared material_config_hash across the verified closed set.
    """
    required = tuple(ACTIVE_REQUIRED_POLICY_IDS)
    invalid: list[str] = []
    observed_contracts: set[str] = set()
    claims_active = False
    has_corruption = False
    by_policy: dict[str, ProductionPolicySnapshot] = {}

    for snap in snapshots:
        observed_contracts.add(snap.contract_id.value)
        if snap.contract_id.value == ACTIVE_SNAPSHOT_BINDING_CONTRACT:
            claims_active = True
        if snap.compatibility_id != compatibility_id:
            has_corruption = True
            invalid.append(snap.policy_id)
            continue
        if snap.purpose.value != purpose_value:
            has_corruption = True
            invalid.append(snap.policy_id)
            continue
        try:
            validate_policy_snapshot_integrity(snap)
        except LearningContractError:
            has_corruption = True
            invalid.append(snap.policy_id)
            continue
        if snap.learning_observation_contract_id != expected_learning_observation_contract_id:
            has_corruption = True
            invalid.append(snap.policy_id)
            continue
        if snap.producer_observation_contract != expected_producer_observation_contract:
            has_corruption = True
            invalid.append(snap.policy_id)
            continue
        if snap.policy_id in by_policy:
            has_corruption = True
            invalid.append(snap.policy_id)
            continue
        # Active v2 rows must match production descriptors; unknown policy under
        # v2 contract is also invalid.
        if snap.contract_id.value == ACTIVE_SNAPSHOT_BINDING_CONTRACT:
            if snap.policy_id not in ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2:
                has_corruption = True
                invalid.append(snap.policy_id)
                continue
            if not _snapshot_matches_production_descriptor(snap):
                has_corruption = True
                invalid.append(snap.policy_id)
                continue
            if snap.policy_version != PRODUCTION_POLICY_VERSION_V1:
                has_corruption = True
                invalid.append(snap.policy_id)
                continue
        by_policy[snap.policy_id] = snap

    if (
        LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1.value in observed_contracts
        and LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2.value in observed_contracts
    ):
        has_corruption = True
        claims_active = True

    if LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V2.value in observed_contracts:
        claims_active = True

    verified_active_ids: list[str] = []
    for pid in required:
        snap = by_policy.get(pid)
        if snap is None:
            continue
        if snap.contract_id.value != ACTIVE_SNAPSHOT_BINDING_CONTRACT:
            continue
        if pid in invalid:
            continue
        verified_active_ids.append(pid)

    missing = tuple(pid for pid in required if pid not in verified_active_ids)
    extra = tuple(
        sorted(
            pid
            for pid in by_policy
            if pid not in required
            and by_policy[pid].contract_id.value == ACTIVE_SNAPSHOT_BINDING_CONTRACT
        )
    )

    # Single material hash across the verified closed set (production identity).
    material_hashes = tuple(
        sorted(
            {by_policy[pid].material_config_hash for pid in verified_active_ids if pid in by_policy}
        )
    )
    if verified_active_ids and len(material_hashes) != 1:
        has_corruption = True
        # Mark all active rows invalid when material identity splits.
        for pid in verified_active_ids:
            invalid.append(pid)
        verified_active_ids = []
        missing = tuple(required)

    v1_only = (
        observed_contracts == {LearningContractId.PRODUCTION_POLICY_SNAPSHOT_V1.value}
        and set(by_policy) >= set(ACCUMULATION_PRODUCTION_POLICY_IDS_V1)
        and not has_corruption
    )
    if v1_only:
        claims_active = False

    active_set_verified = (
        not has_corruption
        and not missing
        and not extra
        and not invalid
        and len(verified_active_ids) == len(required)
        and claims_active
        and len(material_hashes) == 1
    )

    return SnapshotBindingReport(
        binding_contract=ACTIVE_SNAPSHOT_BINDING_CONTRACT,
        required_policy_ids=required,
        required_count=len(required),
        verified_count=len(verified_active_ids),
        verified_policy_ids=tuple(verified_active_ids),
        missing_policy_ids=missing,
        extra_policy_ids=extra,
        invalid_policy_ids=tuple(sorted(set(invalid))),
        observed_contract_ids=tuple(sorted(observed_contracts)),
        material_config_hashes=material_hashes,
        active_set_verified=active_set_verified,
        has_corruption=has_corruption,
        claims_active_binding=claims_active,
    )


def parse_canonical_session_date(raw: Any) -> date | None:
    """Parse a complete canonical YYYY-MM-DD string; reject prefixes and junk."""
    if not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not _SESSION_DATE_RE.fullmatch(candidate):
        return None
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def parse_window_id(window_id: str) -> tuple[str, date] | None:
    """Parse production ``window_id = {TICKER}:{YYYY-MM-DD}`` (ADR-056)."""
    if not isinstance(window_id, str):
        return None
    match = _WINDOW_ID_RE.fullmatch(window_id.strip().upper())
    if match is None:
        return None
    ticker, day_s = match.group(1), match.group(2)
    try:
        return ticker, date.fromisoformat(day_s)
    except ValueError:
        return None


def observation_session_date(observation: LearningObservation) -> date | None:
    """Economic session date only when bound to production identity.

    Requires payload ``session_date`` to agree with ``window_id`` ticker/date and
    payload ticker. Unbound payload date strings do not count as sessions.
    """
    bound = bound_economic_session(observation)
    return bound[1] if bound is not None else None


def bound_economic_session(
    observation: LearningObservation,
) -> tuple[str, date] | None:
    """Return ``(ticker, session_date)`` only when production session binds hold.

    Production write path (AccumulationCandidateObservationPersister):
    - ``window_id = {TICKER}:{YYYY-MM-DD}``
    - payload ``ticker`` and ``session_date`` equal that pair
    - optional ``shared.provenance.latest_completed_session`` when present must
      equal the economic session date

    Does not invent a session from ``cutoff_at`` alone.
    """
    window = parse_window_id(observation.window_id)
    if window is None:
        return None
    win_ticker, win_date = window

    payload = observation.decision_payload
    if not isinstance(payload, Mapping):
        return None
    raw_ticker = payload.get("ticker")
    if not isinstance(raw_ticker, str) or not raw_ticker.strip():
        return None
    payload_ticker = raw_ticker.strip().upper()
    if payload_ticker != win_ticker:
        return None

    session = parse_canonical_session_date(payload.get("session_date"))
    if session is None or session != win_date:
        return None

    return win_ticker, session


def _session_binding_reasons(observation: LearningObservation) -> list[str]:
    """Diagnostic reasons when session is not production-bound."""
    reasons: list[str] = []
    window = parse_window_id(observation.window_id)
    if window is None:
        reasons.append(f"window_id_malformed:{observation.window_id!r}")
        return reasons
    win_ticker, win_date = window

    payload = observation.decision_payload
    if not isinstance(payload, Mapping):
        reasons.append("payload_not_mapping")
        return reasons

    raw_ticker = payload.get("ticker")
    if not isinstance(raw_ticker, str) or not raw_ticker.strip():
        reasons.append("payload_ticker_missing")
    else:
        payload_ticker = raw_ticker.strip().upper()
        if payload_ticker != win_ticker:
            reasons.append(f"ticker_window_mismatch:payload={payload_ticker},window={win_ticker}")

    session = parse_canonical_session_date(payload.get("session_date"))
    if session is None:
        reasons.append("missing_or_malformed_session_date")
    elif session != win_date:
        reasons.append(
            f"session_date_window_mismatch:payload={session.isoformat()},"
            f"window={win_date.isoformat()}"
        )
    return reasons


def _production_payload_semantic_reasons(
    observation: LearningObservation,
    *,
    session: date | None,
) -> list[str]:
    """Fail-closed checks for production session payload shape (writer locks).

    Mirrors ``build_session_observation_payload`` + persister-stamped provenance.
    Does not invent a required payload ``observation_contract`` field (production
    does not stamp it); outer ``contract_id`` remains the learning contract authority.
    """
    reasons: list[str] = []
    if observation.schema_version != ACTIVE_OUTER_SCHEMA_VERSION:
        reasons.append(
            f"outer_schema_version:{observation.schema_version}"
            f"!=expected:{ACTIVE_OUTER_SCHEMA_VERSION}"
        )

    payload = observation.decision_payload
    if not isinstance(payload, Mapping):
        reasons.append("payload_not_mapping")
        return reasons

    artifact_type = payload.get("artifact_type")
    if artifact_type != ACTIVE_SESSION_ARTIFACT_TYPE:
        reasons.append(f"artifact_type:{artifact_type!r}")

    payload_schema = payload.get("schema_version")
    if payload_schema != ACTIVE_PAYLOAD_SCHEMA_VERSION:
        reasons.append(
            f"payload_schema_version:{payload_schema!r}!=expected:{ACTIVE_PAYLOAD_SCHEMA_VERSION}"
        )

    workflow = payload.get("workflow")
    if workflow != ACTIVE_SESSION_WORKFLOW:
        reasons.append(f"workflow:{workflow!r}")

    horizon_primary = payload.get("horizon_primary")
    if horizon_primary != ACTIVE_SESSION_HORIZON_PRIMARY:
        reasons.append(f"horizon_primary:{horizon_primary!r}")

    try:
        canonical_window = int(payload.get("canonical_window"))
    except (TypeError, ValueError):
        reasons.append(f"canonical_window:{payload.get('canonical_window')!r}")
    else:
        if canonical_window != ACTIVE_CANONICAL_WINDOW:
            reasons.append(
                f"canonical_window:{canonical_window}!=expected:{ACTIVE_CANONICAL_WINDOW}"
            )

    features = payload.get("features_by_window")
    if not isinstance(features, Mapping):
        reasons.append("features_by_window_missing")
    else:
        keys = {str(k) for k in features}
        if keys != ACTIVE_FEATURES_WINDOWS:
            reasons.append(f"features_by_window_keys:{sorted(keys)}")

    shared = payload.get("shared")
    if not isinstance(shared, Mapping):
        reasons.append("shared_missing")
    else:
        raw_price = shared.get("current_price")
        try:
            price_ok = raw_price is not None and float(raw_price) > 0
        except (TypeError, ValueError):
            price_ok = False
        if not price_ok:
            reasons.append(f"shared.current_price:{raw_price!r}")

        # Active ACCUM path always stamps provenance; required for challenge readiness.
        provenance = shared.get("provenance")
        if not isinstance(provenance, Mapping) or not provenance:
            reasons.append("shared.provenance_missing")
        else:
            if (
                "decision_at" not in provenance
                or not str(provenance.get("decision_at") or "").strip()
            ):
                reasons.append("shared.provenance.decision_at_missing")
            latest = provenance.get("latest_completed_session")
            latest_date = parse_canonical_session_date(latest)
            if latest_date is None:
                reasons.append("shared.provenance.latest_completed_session_malformed")
            elif session is not None and latest_date != session:
                reasons.append(
                    "provenance_session_mismatch:"
                    f"latest={latest_date.isoformat()},session={session.isoformat()}"
                )

    # Optional payload contract fields: if present, must match active producer contract.
    for key in ("observation_contract", "producer_observation_contract"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            if raw.strip() != ACTIVE_PRODUCER_OBSERVATION_CONTRACT:
                reasons.append(f"{key}:{raw.strip()}")

    return reasons


def validate_observation_cohort(
    observations: Sequence[LearningObservation],
    *,
    purpose_value: str,
    compatibility_id: str,
    expected_learning_observation_contract_id: str = ACTIVE_LEARNING_OBSERVATION_CONTRACT,
    expected_producer_observation_contract: str = ACTIVE_PRODUCER_OBSERVATION_CONTRACT,
) -> ObservationCohortValidation:
    """Validate every observation: digest, identity, schema, producer payload, session."""
    reasons: list[str] = []
    session_dates: set[date] = set()
    valid = 0
    invalid = 0

    for obs in observations:
        obs_reasons: list[str] = []
        try:
            validate_artifact_integrity(obs, id_field="observation_id")
        except LearningContractError:
            obs_reasons.append("artifact_digest_mismatch")
        try:
            validate_observation_identity(obs)
        except LearningContractError:
            obs_reasons.append("observation_id_mismatch")
        if obs.purpose.value != purpose_value:
            obs_reasons.append(f"purpose:{obs.purpose.value}")
        if obs.compatibility_id != compatibility_id:
            obs_reasons.append("compatibility_id_mismatch")
        if obs.contract_id.value != expected_learning_observation_contract_id:
            obs_reasons.append(f"contract_id:{obs.contract_id.value}")
        # Active ACCUM discovery production write locks (persister + ADR-056).
        if purpose_value == AssessmentPurpose.ACCUMULATION_DISCOVERY.value:
            if obs.policy_contract != ACTIVE_POLICY_CONTRACT:
                obs_reasons.append(f"policy_contract:{obs.policy_contract}")
            if obs.horizon_contract != ACTIVE_HORIZON_CONTRACT:
                obs_reasons.append(f"horizon_contract:{obs.horizon_contract}")
            # Population authority: membership digest only (not inventable free-form labels).
            # Self-consistent observation_id recomputation is not population proof.
            if not is_accum_population_universe_id(obs.universe_id):
                obs_reasons.append(
                    "population_authority_unbound:"
                    f"universe_id={obs.universe_id!r},"
                    f"contract={ACTIVE_POPULATION_AUTHORITY_CONTRACT}"
                )

        # Authoritative economic session: bound to window_id + ticker.
        bound = bound_economic_session(obs)
        if bound is None:
            obs_reasons.extend(_session_binding_reasons(obs))
            session_for_payload: date | None = None
        else:
            session_for_payload = bound[1]

        # Schema + producer payload semantics (writer shape).
        if purpose_value == AssessmentPurpose.ACCUMULATION_DISCOVERY.value:
            obs_reasons.extend(
                _production_payload_semantic_reasons(obs, session=session_for_payload)
            )

        if obs_reasons:
            invalid += 1
            reasons.append(f"{obs.observation_id}:{','.join(obs_reasons)}")
        else:
            # Only fully valid, bound observations contribute session depth.
            assert bound is not None  # binding reasons would have been recorded
            session_dates.add(bound[1])
            valid += 1

    return ObservationCohortValidation(
        expected_learning_observation_contract_id=expected_learning_observation_contract_id,
        expected_producer_observation_contract=expected_producer_observation_contract,
        valid_observation_count=valid,
        invalid_observation_count=invalid,
        invalid_reasons=tuple(reasons[:50]),
        session_dates=tuple(sorted(session_dates)),
        has_contract_corruption=invalid > 0,
    )


def _canonical_window_key(payload: Mapping[str, Any]) -> str:
    raw = payload.get("canonical_window", 7)
    try:
        return str(int(raw))
    except (TypeError, ValueError):
        return "7"


def extract_action_from_payload(payload: Mapping[str, Any] | Any) -> str | None:
    """Read frozen Action from the session observation payload (no recompute)."""
    if not isinstance(payload, Mapping):
        return None
    features = payload.get("features_by_window")
    if not isinstance(features, Mapping):
        return None
    pack = features.get(_canonical_window_key(payload))
    if not isinstance(pack, Mapping):
        return None
    trade_setup = pack.get("trade_setup")
    if isinstance(trade_setup, Mapping):
        action = trade_setup.get("action")
        if isinstance(action, str) and action.strip():
            return action.strip()
    candidate = pack.get("candidate")
    if isinstance(candidate, Mapping):
        nested = candidate.get("trade_setup")
        if isinstance(nested, Mapping):
            action = nested.get("action")
            if isinstance(action, str) and action.strip():
                return action.strip()
    return None


def extract_setup_readiness_status_from_payload(
    payload: Mapping[str, Any] | Any,
) -> str | None:
    """Read authoritative typed setup-readiness status from payload only.

    Source of truth: ``features_by_window[canonical].signal.setup_readiness``.
    Fingerprint fields are diagnostic only and must not satisfy presence.
    """
    if not isinstance(payload, Mapping):
        return None
    features = payload.get("features_by_window")
    if not isinstance(features, Mapping):
        return None
    pack = features.get(_canonical_window_key(payload))
    if not isinstance(pack, Mapping):
        return None
    signal = pack.get("signal")
    if not isinstance(signal, Mapping):
        return None
    readiness = signal.get("setup_readiness")
    if not isinstance(readiness, Mapping):
        return None
    status = readiness.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    return None


def extract_fingerprint_setup_readiness_status(
    payload: Mapping[str, Any] | Any,
) -> str | None:
    """Diagnostic fingerprint readiness only (never authoritative presence)."""
    if not isinstance(payload, Mapping):
        return None
    features = payload.get("features_by_window")
    if not isinstance(features, Mapping):
        return None
    pack = features.get(_canonical_window_key(payload))
    if not isinstance(pack, Mapping):
        return None
    fingerprint = pack.get("sub_signal_fingerprint")
    if not isinstance(fingerprint, Mapping):
        return None
    status = fingerprint.get("setup_readiness_status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    return None


def count_labels_by_horizon(
    *,
    observation_ids: Sequence[str],
    labels: Sequence[LearningOutcomeLabel],
) -> LabelCohortValidation:
    """Count path labels after digest, identity, basis, and availability↔outcome checks.

    Read-side authority: a rehashed ``AVAILABLE``+``outcome=None`` (or
    ``UNAVAILABLE``+outcome) label is integrity corruption — never counted as a
    normal available/unavailable success and never alone enables
    ``CHALLENGE_INPUT_READY``.

    Multi-row path labels for the same observation + horizon are also
    authority-bearing integrity corruption (``conflict``): they skip AVAILABLE
    tally and set ``has_integrity_corruption`` so classification fails closed.
    """
    obs_set = set(observation_ids)
    by_contract: dict[LearningContractId, list[LearningOutcomeLabel]] = {
        c: [] for c in PATH_LABEL_CONTRACTS
    }
    invalid_reasons: list[str] = []
    invalid_label_count = 0

    for label in labels:
        if label.observation_id not in obs_set:
            continue
        label_reasons: list[str] = []
        try:
            validate_artifact_integrity(label, id_field="label_id")
        except LearningContractError:
            label_reasons.append("artifact_digest_mismatch")
        try:
            validate_label_identity(label)
        except LearningContractError:
            label_reasons.append("label_id_mismatch")
        if label.outcome_basis is not ACTIVE_LABEL_OUTCOME_BASIS:
            label_reasons.append(f"outcome_basis:{label.outcome_basis.value}")
        # Same invariant as LearningOutcomeLabel.create — revalidated after load.
        try:
            validate_label_availability_outcome(label.availability, label.outcome)
        except LearningContractError as exc:
            msg = str(exc)
            if "available label requires" in msg:
                label_reasons.append("available_without_outcome")
            elif "unavailable label cannot" in msg:
                label_reasons.append("unavailable_with_outcome")
            else:
                label_reasons.append(f"availability_outcome:{msg}")
        if label_reasons:
            invalid_label_count += 1
            invalid_reasons.append(f"{label.label_id}:{','.join(label_reasons)}")
            continue
        if label.contract_id in by_contract:
            by_contract[label.contract_id].append(label)

    out: dict[str, LabelHorizonCounts] = {}
    total_conflict = 0
    for contract in PATH_LABEL_CONTRACTS:
        rows = by_contract[contract]
        by_obs: dict[str, list[LearningOutcomeLabel]] = {}
        for row in rows:
            by_obs.setdefault(row.observation_id, []).append(row)

        available = 0
        unavailable = 0
        conflict = 0
        labeled_obs: set[str] = set()
        for obs_id, group in by_obs.items():
            labeled_obs.add(obs_id)
            if len(group) > 1:
                # Authority-bearing multi-row path-label conflict (same observation
                # + horizon). Do not count as AVAILABLE/UNAVAILABLE; fail closed.
                conflict += 1
                total_conflict += 1
                horizon = _HORIZON_KEY_BY_CONTRACT[contract]
                invalid_reasons.append(f"{obs_id}:path_label_conflict:{horizon}:rows={len(group)}")
                continue
            label = group[0]
            if label.availability is LabelAvailability.AVAILABLE:
                available += 1
            elif label.availability is LabelAvailability.UNAVAILABLE:
                unavailable += 1
        insufficient = max(0, len(obs_set) - len(labeled_obs))
        horizon = _HORIZON_KEY_BY_CONTRACT[contract]
        out[horizon] = LabelHorizonCounts(
            available=available,
            unavailable=unavailable,
            insufficient_horizon=insufficient,
            conflict=conflict,
        )
    return LabelCohortValidation(
        counts_by_horizon=out,
        invalid_label_count=invalid_label_count,
        invalid_reasons=tuple(invalid_reasons[:50]),
        # Multi-row path-label conflicts are integrity corruption, not diagnostic-only.
        has_integrity_corruption=invalid_label_count > 0 or total_conflict > 0,
    )


def project_cohort_readiness(
    *,
    compatibility_id: str,
    observations: Sequence[LearningObservation],
    labels: Sequence[LearningOutcomeLabel],
    snapshots: Sequence[ProductionPolicySnapshot],
    purpose_value: str,
    expected_learning_observation_contract_id: str = ACTIVE_LEARNING_OBSERVATION_CONTRACT,
    expected_producer_observation_contract: str = ACTIVE_PRODUCER_OBSERVATION_CONTRACT,
) -> CohortProducerReadiness:
    """Project one cohort's producer readiness from already-loaded artifacts."""
    obs_validation = validate_observation_cohort(
        observations,
        purpose_value=purpose_value,
        compatibility_id=compatibility_id,
        expected_learning_observation_contract_id=expected_learning_observation_contract_id,
        expected_producer_observation_contract=expected_producer_observation_contract,
    )

    action_counts: Counter[str] = Counter()
    readiness_states: Counter[str] = Counter()
    readiness_present = 0
    readiness_missing = 0

    for obs in observations:
        action = extract_action_from_payload(obs.decision_payload)
        action_counts[action if action is not None else "null"] += 1
        readiness = extract_setup_readiness_status_from_payload(obs.decision_payload)
        if readiness is None:
            readiness_missing += 1
            readiness_states["null"] += 1
        else:
            readiness_present += 1
            readiness_states[readiness] += 1

    observation_contract = expected_learning_observation_contract_id
    if observations:
        contracts = sorted({o.contract_id.value for o in observations})
        observation_contract = contracts[0] if len(contracts) == 1 else ",".join(contracts)

    sorted_sessions = list(obs_validation.session_dates)
    economic_min = sorted_sessions[0].isoformat() if sorted_sessions else None
    economic_max = sorted_sessions[-1].isoformat() if sorted_sessions else None
    # Only validated observations contribute to session depth.
    session_count = len(sorted_sessions) if not obs_validation.has_contract_corruption else 0

    snapshot = verify_snapshot_binding(
        snapshots,
        purpose_value=purpose_value,
        compatibility_id=compatibility_id,
        expected_learning_observation_contract_id=expected_learning_observation_contract_id,
        expected_producer_observation_contract=expected_producer_observation_contract,
    )
    valid_ids = [
        o.observation_id
        for o in observations
        if o.purpose.value == purpose_value
        and o.compatibility_id == compatibility_id
        and o.contract_id.value == expected_learning_observation_contract_id
        and observation_session_date(o) is not None
    ]
    if obs_validation.has_contract_corruption:
        label_ids = [o.observation_id for o in observations]
    else:
        label_ids = valid_ids

    label_validation = count_labels_by_horizon(
        observation_ids=label_ids,
        labels=labels,
    )
    labels_by_horizon = label_validation.counts_by_horizon
    h10 = labels_by_horizon["H10"]
    blocked = obs_validation.has_contract_corruption or label_validation.has_integrity_corruption
    status = classify_producer_status(
        snapshot=snapshot,
        observation_validation=obs_validation,
        label_validation=label_validation,
        session_count=session_count,
        available_h10_labels=0 if blocked else h10.available,
    )
    return CohortProducerReadiness(
        compatibility_id=compatibility_id,
        observation_contract=observation_contract,
        observation_count=len(observations),
        session_count=session_count,
        economic_date_min=economic_min,
        economic_date_max=economic_max,
        snapshot=snapshot,
        observation_validation=obs_validation,
        label_validation=label_validation,
        labels_by_horizon=labels_by_horizon,
        action_distribution=dict(sorted(action_counts.items())),
        setup_readiness_present=readiness_present,
        setup_readiness_missing=readiness_missing,
        setup_readiness_state_distribution=dict(sorted(readiness_states.items())),
        producer_status=status,
    )


def cohort_to_dict(cohort: CohortProducerReadiness) -> dict[str, Any]:
    """JSON-stable dict for CLI / operator surfaces."""
    labels = {
        key: {
            "available": value.available,
            "unavailable": value.unavailable,
            "insufficient_horizon": value.insufficient_horizon,
            "conflict": value.conflict,
        }
        for key, value in cohort.labels_by_horizon.items()
    }
    snap = cohort.snapshot
    ov = cohort.observation_validation
    return {
        "compatibility_id": cohort.compatibility_id,
        "observation_contract": cohort.observation_contract,
        "observation_count": cohort.observation_count,
        "session_count": cohort.session_count,
        "economic_date_min": cohort.economic_date_min,
        "economic_date_max": cohort.economic_date_max,
        "snapshot_binding_contract": snap.binding_contract,
        "snapshot_required_count": snap.required_count,
        "snapshot_verified_count": snap.verified_count,
        "snapshot_verified_policy_ids": list(snap.verified_policy_ids),
        "snapshot_missing_policy_ids": list(snap.missing_policy_ids),
        "snapshot_extra_policy_ids": list(snap.extra_policy_ids),
        "snapshot_invalid_policy_ids": list(snap.invalid_policy_ids),
        "snapshot_observed_contract_ids": list(snap.observed_contract_ids),
        "snapshot_material_config_hashes": list(snap.material_config_hashes),
        "snapshot_active_set_verified": snap.active_set_verified,
        "observation_valid_count": ov.valid_observation_count,
        "observation_invalid_count": ov.invalid_observation_count,
        "observation_invalid_reasons": list(ov.invalid_reasons),
        "observation_contract_corruption": ov.has_contract_corruption,
        "label_invalid_count": cohort.label_validation.invalid_label_count,
        "label_invalid_reasons": list(cohort.label_validation.invalid_reasons),
        "label_integrity_corruption": cohort.label_validation.has_integrity_corruption,
        "labels_by_horizon": labels,
        "action_distribution": dict(cohort.action_distribution),
        "setup_readiness_present": cohort.setup_readiness_present,
        "setup_readiness_missing": cohort.setup_readiness_missing,
        "setup_readiness_state_distribution": dict(cohort.setup_readiness_state_distribution),
        "producer_status": cohort.producer_status.value,
    }
