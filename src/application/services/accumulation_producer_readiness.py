"""Pure producer readiness projection for accumulation challenge corpus (P0).

Layer: Application (pure). No I/O. Classifies each explicit compatibility cohort
using locked rules from grow_snapshot_bound_accum_challenge_corpus.md.

Producer status is a handoff gate, not an ML fold/verdict.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Sequence

from src.application.services.accumulation_production_policy_descriptors import (
    ACCUMULATION_PRODUCTION_POLICY_DESCRIPTORS_V2,
)
from src.application.services.lean_observation_identity import (
    POLICY_SNAPSHOT_BINDING_CONTRACT_V2,
)
from src.domain.ports.trading_session_calendar_repository import (
    TradingSessionCalendarSnapshotReadError,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
from src.domain.value_objects.learning_artifacts import (
    ACCUM_POPULATION_AUTHORITY_CONTRACT,
    ACCUMULATION_PRODUCTION_POLICY_IDS_V1,
    ACCUMULATION_PRODUCTION_POLICY_IDS_V2,
    LEARNING_SCHEMA_VERSION,
    PRODUCTION_POLICY_VERSION_V1,
    AccumPopulationBinding,
    AssessmentPurpose,
    LabelAvailability,
    LearningContractError,
    LearningContractId,
    LearningObservation,
    LearningOutcomeLabel,
    OutcomeBasis,
    ProductionPolicySnapshot,
    is_accum_population_universe_id,
    recompute_path_label_fingerprint,
    validate_accum_population_binding,
    validate_artifact_integrity,
    validate_label_availability_outcome,
    validate_label_identity,
    validate_observation_identity,
    validate_policy_snapshot_integrity,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    INCOMPLETE_POPULATION_ATTESTATION_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
    LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_observation_contracts import (
    ACCUMULATION_DISCOVERY_HORIZON_CONTRACT,
    ACCUMULATION_DISCOVERY_OBSERVATION_CONTRACT,
    ACCUMULATION_DISCOVERY_POLICY_CONTRACT,
)
from src.domain.value_objects.trading_session_calendar_snapshot import (
    PATH_LABEL_METRICS_SCHEMA_VERSION,
    STOCKBIT_TRADING_SESSIONS_CONTRACT,
    TRADING_SESSION_CALENDAR_BENCHMARK_IHSG,
    TRADING_SESSION_CALENDAR_SOURCE_STOCKBIT,
    TradingSessionCalendarSnapshot,
    label_window_digest,
    validate_active_stockbit_calendar_snapshot,
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
# Population authority for ACCUM challenge inputs (Option A typed binding).
# A 64-hex universe_id alone is never sufficient.
ACTIVE_POPULATION_AUTHORITY_CONTRACT = ACCUM_POPULATION_AUTHORITY_CONTRACT
LEGACY_PAYLOAD_SCHEMA_VERSION = LEGACY_CANDIDATE_OBSERVATION_SCHEMA_VERSION
# Schema-10 incomplete population surface (pre-attested tickers): non-current.
INCOMPLETE_PAYLOAD_SCHEMA_VERSION = (
    INCOMPLETE_POPULATION_ATTESTATION_CANDIDATE_OBSERVATION_SCHEMA_VERSION
)
# Non-current ACCUM payload schemas that must not be revalidated as current.
NON_CURRENT_PAYLOAD_SCHEMA_VERSIONS: frozenset[int] = frozenset(
    {
        LEGACY_PAYLOAD_SCHEMA_VERSION,
        INCOMPLETE_PAYLOAD_SCHEMA_VERSION,
    }
)

# Horizon nicknames for operator-facing reports (H3/H10/H20).
_HORIZON_KEY_BY_CONTRACT: Mapping[LearningContractId, str] = {
    LearningContractId.ACCUM_3D_LABEL: "H3",
    LearningContractId.ACCUM_10D_LABEL: "H10",
    LearningContractId.ACCUM_20D_LABEL: "H20",
}
_PATH_LABEL_HORIZON_DAYS: Mapping[LearningContractId, int] = {
    LearningContractId.ACCUM_3D_LABEL: 3,
    LearningContractId.ACCUM_10D_LABEL: 10,
    LearningContractId.ACCUM_20D_LABEL: 20,
}
_ALLOWED_PATH_OUTCOMES: frozenset[str] = frozenset({"SUCCESS", "FAILURE", "NEUTRAL"})
# Production ACCUM path-label generator emits this exact terminal UNAVAILABLE reason
# (database_learning_lifecycle_use_case). Not free-form; not parameterized CA strings.
_SUPPORTED_PATH_UNAVAILABLE_REASONS: frozenset[str] = frozenset(
    {
        "corporate_action_in_window",
    }
)
_AVAILABLE_METRIC_KEYS: frozenset[str] = frozenset(
    {
        "ticker",
        "signal_date",
        "label_window_start",
        "label_window_end",
        "label_window_sessions",
        "calendar_snapshot_id",
        "calendar_contract_id",
        "calendar_source_revision",
        "label_window_digest",
        "path_label_metrics_schema_version",
        "entry_reference_price",
        "close_return_pct",
        "max_forward_return_pct",
        "max_adverse_excursion_pct",
        "days_to_peak",
        "days_to_trough",
    }
)


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
    # True when at least one observation passes full current schema + binding authority.
    has_current_population_authority: bool = False
    legacy_observation_count: int = 0
    # Observation IDs that individually passed validation (current-authority or
    # schema-9 legacy). Invalid / authority-corrupt rows are excluded. Action,
    # setup-readiness, and label tallies must use only this set.
    validated_observation_ids: tuple[str, ...] = ()


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
    has_current_population_authority: bool | None = None,
) -> ProducerReadinessStatus:
    """Apply locked precedence rules for one cohort.

    Rules (exact):
    - LEGACY_RAW_ONLY: observations exist under absent/unknown/historical binding
      (including schema-9 without population_binding) without snapshot corruption
      and without observation/label corruption. Pure schema-9 only — never when
      mixed with current-authority rows.
    - BLOCKED_POLICY: active binding claimed but set partial/mixed/malformed/
      invalid/mismatched, any snapshot corruption, observation contract/
      provenance/digest/population corruption, mixed non-current+current cohort,
      or label digest corruption.
    - COLLECTING: exact active snapshots verify, current population authority
      present, observations+labels validate, but <2 sessions or zero AVAILABLE
      primary H10 labels.
    - CHALLENGE_INPUT_READY: exact active snapshots verify, current population
      authority present, observations+labels validate, ≥2 sessions, and ≥1
      AVAILABLE price_path.accum_10d.v1 label. Homogeneous current cohort only.
    """
    current_authority = (
        observation_validation.has_current_population_authority
        if has_current_population_authority is None
        else has_current_population_authority
    )
    if (
        snapshot.has_corruption
        or observation_validation.has_contract_corruption
        or label_validation.has_integrity_corruption
        or (snapshot.claims_active_binding and not snapshot.active_set_verified)
    ):
        return ProducerReadinessStatus.BLOCKED_POLICY
    if not snapshot.active_set_verified:
        return ProducerReadinessStatus.LEGACY_RAW_ONLY
    if not current_authority:
        # Schema-9 / unbound historical corpus even when active snapshots exist.
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
        if snap.schema_version != LEARNING_SCHEMA_VERSION:
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


def _parse_aware_datetime(raw: Any) -> datetime | None:
    """Parse ISO datetime requiring timezone awareness; reject naive/junk."""
    if isinstance(raw, datetime):
        if raw.tzinfo is None or raw.utcoffset() is None:
            return None
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _datetimes_equal(a: datetime, b: datetime) -> bool:
    """Timezone-aware equality via UTC instants."""
    return a.astimezone().timestamp() == b.astimezone().timestamp()


def _production_payload_semantic_reasons(
    observation: LearningObservation,
    *,
    session: date | None,
    require_current_payload_schema: bool = True,
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
    if require_current_payload_schema and payload_schema != ACTIVE_PAYLOAD_SCHEMA_VERSION:
        reasons.append(
            f"payload_schema_version:{payload_schema!r}!=expected:{ACTIVE_PAYLOAD_SCHEMA_VERSION}"
        )

    workflow = payload.get("workflow")
    if workflow != ACTIVE_SESSION_WORKFLOW:
        reasons.append(f"workflow:{workflow!r}")

    horizon_primary = payload.get("horizon_primary")
    if horizon_primary != ACTIVE_SESSION_HORIZON_PRIMARY:
        reasons.append(f"horizon_primary:{horizon_primary!r}")

    raw_canonical_window = payload.get("canonical_window")
    if type(raw_canonical_window) is not int:
        reasons.append(f"canonical_window:{raw_canonical_window!r}")
    elif raw_canonical_window != ACTIVE_CANONICAL_WINDOW:
        reasons.append(
            f"canonical_window:{raw_canonical_window}!=expected:{ACTIVE_CANONICAL_WINDOW}"
        )

    features = payload.get("features_by_window")
    if not isinstance(features, Mapping):
        reasons.append("features_by_window_missing")
    else:
        keys = {str(k) for k in features}
        if keys != ACTIVE_FEATURES_WINDOWS:
            reasons.append(f"features_by_window_keys:{sorted(keys)}")

    # Payload captured_at must equal outer captured_at (PIT capture authority).
    payload_captured = _parse_aware_datetime(payload.get("captured_at"))
    if payload_captured is None:
        reasons.append(f"payload.captured_at_malformed:{payload.get('captured_at')!r}")
    else:
        outer_captured = observation.captured_at
        if (
            outer_captured.tzinfo is None
            or outer_captured.utcoffset() is None
            or not _datetimes_equal(payload_captured, outer_captured)
        ):
            reasons.append(
                "captured_at_mismatch:"
                f"payload={payload.get('captured_at')!r},"
                f"outer={outer_captured.isoformat()!r}"
            )

    shared = payload.get("shared")
    if not isinstance(shared, Mapping):
        reasons.append("shared_missing")
    else:
        raw_price = shared.get("current_price")
        # Exact int/float only — reject bool/string/non-finite/non-positive.
        if type(raw_price) is bool or type(raw_price) not in (int, float):
            reasons.append(f"shared.current_price:{raw_price!r}")
        else:
            try:
                price_ok = (
                    raw_price > 0 and raw_price == raw_price and abs(raw_price) != float("inf")
                )
            except (TypeError, ValueError):
                price_ok = False
            if not price_ok:
                reasons.append(f"shared.current_price:{raw_price!r}")

        # Active ACCUM path always stamps provenance; required for challenge readiness.
        provenance = shared.get("provenance")
        if not isinstance(provenance, Mapping) or not provenance:
            reasons.append("shared.provenance_missing")
        else:
            decision_at = _parse_aware_datetime(provenance.get("decision_at"))
            if decision_at is None:
                reasons.append(
                    f"shared.provenance.decision_at_malformed:{provenance.get('decision_at')!r}"
                )
            else:
                cutoff = observation.cutoff_at
                if (
                    cutoff.tzinfo is None
                    or cutoff.utcoffset() is None
                    or not _datetimes_equal(decision_at, cutoff)
                ):
                    reasons.append(
                        "decision_at_cutoff_mismatch:"
                        f"decision_at={provenance.get('decision_at')!r},"
                        f"cutoff_at={cutoff.isoformat()!r}"
                    )
            latest = provenance.get("latest_completed_session")
            latest_date = parse_canonical_session_date(latest)
            if latest_date is None:
                reasons.append("shared.provenance.latest_completed_session_malformed")
            elif session is not None and latest_date != session:
                reasons.append(
                    "provenance_session_mismatch:"
                    f"latest={latest_date.isoformat()},session={session.isoformat()}"
                )
            analysis_as_of = parse_canonical_session_date(provenance.get("analysis_as_of"))
            if analysis_as_of is None:
                reasons.append(
                    "shared.provenance.analysis_as_of_malformed:"
                    f"{provenance.get('analysis_as_of')!r}"
                )
            elif session is not None and analysis_as_of != session:
                reasons.append(
                    "analysis_as_of_session_mismatch:"
                    f"analysis_as_of={analysis_as_of.isoformat()},"
                    f"session={session.isoformat()}"
                )

    # Option A population binding (current payload schema authority only).
    if require_current_payload_schema:
        reasons.extend(_population_binding_reasons(observation, session=session, payload=payload))

    # Optional payload contract fields: if present, must match active producer contract.
    for key in ("observation_contract", "producer_observation_contract"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            if raw.strip() != ACTIVE_PRODUCER_OBSERVATION_CONTRACT:
                reasons.append(f"{key}:{raw.strip()}")

    return reasons


def _population_binding_reasons(
    observation: LearningObservation,
    *,
    session: date | None,
    payload: Mapping[str, Any],
) -> list[str]:
    """Validate typed population_binding; 64-hex universe_id alone never suffices."""
    reasons: list[str] = []
    # Shape of outer universe_id is necessary but not sufficient.
    if not is_accum_population_universe_id(observation.universe_id):
        reasons.append(
            "population_authority_unbound:"
            f"universe_id={observation.universe_id!r},"
            f"contract={ACTIVE_POPULATION_AUTHORITY_CONTRACT}"
        )
        return reasons

    raw_binding = payload.get("population_binding")
    if raw_binding is None:
        reasons.append(
            "population_authority_unbound:missing_population_binding,"
            f"contract={ACTIVE_POPULATION_AUTHORITY_CONTRACT}"
        )
        return reasons
    try:
        binding = AccumPopulationBinding.from_mapping(raw_binding)
        validate_accum_population_binding(
            binding,
            outer_universe_id=observation.universe_id,
            economic_session=session,
        )
    except LearningContractError as exc:
        reasons.append(f"population_authority_unbound:{exc}")
    return reasons


def validate_observation_cohort(
    observations: Sequence[LearningObservation],
    *,
    purpose_value: str,
    compatibility_id: str,
    expected_learning_observation_contract_id: str = ACTIVE_LEARNING_OBSERVATION_CONTRACT,
    expected_producer_observation_contract: str = ACTIVE_PRODUCER_OBSERVATION_CONTRACT,
) -> ObservationCohortValidation:
    """Validate every observation: digest, identity, schema, producer payload, session.

    Schema-9 ACCUM rows without population_binding and schema-10 incomplete
    (pre-attested ticker sets) are immutable non-current corpus — not
    revalidated as the current schema and not current challenge authority.
    Current payload schema requires complete typed binding with attested
    ticker sets and full PIT/provenance equalities.
    """
    reasons: list[str] = []
    current_session_dates: set[date] = set()
    legacy_session_dates: set[date] = set()
    validated_ids: list[str] = []
    valid = 0
    invalid = 0
    legacy_count = 0
    current_authority_count = 0

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

        payload = obs.decision_payload if isinstance(obs.decision_payload, Mapping) else {}
        payload_schema = payload.get("schema_version") if isinstance(payload, Mapping) else None
        is_non_current_payload = (
            purpose_value == AssessmentPurpose.ACCUMULATION_DISCOVERY.value
            and payload_schema in NON_CURRENT_PAYLOAD_SCHEMA_VERSIONS
        )
        is_legacy_payload = is_non_current_payload
        is_current_payload = (
            purpose_value == AssessmentPurpose.ACCUMULATION_DISCOVERY.value
            and payload_schema == ACTIVE_PAYLOAD_SCHEMA_VERSION
        )

        # Active ACCUM discovery production write locks (persister + ADR-056).
        if purpose_value == AssessmentPurpose.ACCUMULATION_DISCOVERY.value:
            if obs.policy_contract != ACTIVE_POLICY_CONTRACT:
                obs_reasons.append(f"policy_contract:{obs.policy_contract}")
            if obs.horizon_contract != ACTIVE_HORIZON_CONTRACT:
                obs_reasons.append(f"horizon_contract:{obs.horizon_contract}")
            # Free-form inventable universe_id is always unbound corruption.
            if not is_accum_population_universe_id(obs.universe_id):
                obs_reasons.append(
                    "population_authority_unbound:"
                    f"universe_id={obs.universe_id!r},"
                    f"contract={ACTIVE_POPULATION_AUTHORITY_CONTRACT}"
                )
            elif is_current_payload:
                # Current schema: hex alone never suffices — validated in payload semantics.
                pass
            elif is_non_current_payload:
                # Schema-9 / incomplete schema-10: historical; not current authority.
                pass
            else:
                # Unknown/missing payload schema with hex universe is not current authority.
                # Treat as corruption when it claims neither non-current nor current schema.
                if payload_schema not in (None, *NON_CURRENT_PAYLOAD_SCHEMA_VERSIONS):
                    obs_reasons.append(
                        f"payload_schema_version:{payload_schema!r}"
                        f"!=expected:{ACTIVE_PAYLOAD_SCHEMA_VERSION}"
                    )

        # Authoritative economic session: bound to window_id + ticker.
        bound = bound_economic_session(obs)
        if bound is None:
            obs_reasons.extend(_session_binding_reasons(obs))
            session_for_payload: date | None = None
        else:
            session_for_payload = bound[1]

        # Schema + producer payload semantics (writer shape).
        # Non-current rows are not revalidated under the current schema contract;
        # they remain LEGACY_RAW_ONLY when digests/identity hold and no other corruption.
        if purpose_value == AssessmentPurpose.ACCUMULATION_DISCOVERY.value:
            if is_non_current_payload:
                pass
            elif is_current_payload:
                obs_reasons.extend(
                    _production_payload_semantic_reasons(
                        obs,
                        session=session_for_payload,
                        require_current_payload_schema=True,
                    )
                )
            else:
                # Missing/foreign schema: require current contract (fail closed).
                obs_reasons.extend(
                    _production_payload_semantic_reasons(
                        obs,
                        session=session_for_payload,
                        require_current_payload_schema=True,
                    )
                )

        if obs_reasons:
            invalid += 1
            reasons.append(f"{obs.observation_id}:{','.join(obs_reasons)}")
        elif is_legacy_payload:
            # Valid historical row: digests/identity OK, no current authority.
            validated_ids.append(obs.observation_id)
            legacy_count += 1
            if bound is not None:
                legacy_session_dates.add(bound[1])
        else:
            # Fully valid current-authority observation contributes session depth.
            assert bound is not None  # binding reasons would have been recorded
            validated_ids.append(obs.observation_id)
            current_session_dates.add(bound[1])
            valid += 1
            current_authority_count += 1

    # Cohorts never mix non-current historical and current authority.
    # Coexistence is authority-bearing corruption even when each row is valid
    # in isolation — READY must not follow from "any current row exists".
    mixed_schema_cohort = legacy_count > 0 and current_authority_count > 0
    if mixed_schema_cohort:
        reasons.append(
            f"mixed_schema_cohort:legacy={legacy_count},current={current_authority_count}"
        )

    # Option A: producer-attested cohort invariants (not reverse of compatibility hash).
    # Current-authority rows in one compatibility cohort must share lookback and
    # named-roster identity material.
    cohort_invariant_reasons = _cohort_population_invariant_reasons(
        [
            o
            for o in observations
            if o.observation_id in validated_ids
            and isinstance(o.decision_payload, Mapping)
            and o.decision_payload.get("schema_version") == ACTIVE_PAYLOAD_SCHEMA_VERSION
        ]
    )
    if cohort_invariant_reasons:
        reasons.extend(cohort_invariant_reasons)
        # Cohort-invariant split: no row remains authoritative under this cohort.
        invalid += current_authority_count
        valid = 0
        validated_ids = []
        current_session_dates = set()
        current_authority_count = 0

    # Readiness session depth uses current-authority sessions only when present;
    # otherwise report legacy diagnostic sessions (LEGACY_RAW_ONLY path).
    report_sessions = current_session_dates if current_authority_count > 0 else legacy_session_dates
    has_corruption = invalid > 0 or mixed_schema_cohort or bool(cohort_invariant_reasons)

    return ObservationCohortValidation(
        expected_learning_observation_contract_id=expected_learning_observation_contract_id,
        expected_producer_observation_contract=expected_producer_observation_contract,
        valid_observation_count=valid,
        invalid_observation_count=invalid,
        invalid_reasons=tuple(reasons[:50]),
        session_dates=tuple(sorted(report_sessions)),
        # Current-authority corruption, digest/identity failures, or mixed
        # non-current + current coexistence block. Pure non-current alone
        # is not contract corruption.
        has_contract_corruption=has_corruption,
        has_current_population_authority=current_authority_count > 0,
        legacy_observation_count=legacy_count,
        validated_observation_ids=tuple(validated_ids),
    )


def _cohort_population_invariant_reasons(
    current_observations: Sequence[LearningObservation],
) -> list[str]:
    """Require equal cohort-invariant population fields across current rows.

    Option A (producer attestation): compatibility_id does not cryptographically
    prove lookback; typed equality of attested invariants is the authority.
    """
    if len(current_observations) < 2:
        return []
    fingerprints: list[tuple[str, tuple[Any, ...]]] = []
    for obs in current_observations:
        payload = obs.decision_payload
        if not isinstance(payload, Mapping):
            continue
        raw = payload.get("population_binding")
        if not isinstance(raw, Mapping):
            continue
        try:
            binding = AccumPopulationBinding.from_mapping(raw)
        except LearningContractError as exc:
            return [f"cohort_population_invariant:{exc}"]
        fp = (
            binding.schema_version,
            binding.contract_id,
            binding.population_name,
            binding.named_universe_digest,
            binding.named_universe_tickers,
            binding.tradable_membership_contract,
            binding.pit_tradable_lookback_sessions,
            binding.benchmark_symbol,
        )
        fingerprints.append((obs.observation_id, fp))
    if len(fingerprints) < 2:
        return []
    reference = fingerprints[0][1]
    for obs_id, fp in fingerprints[1:]:
        if fp != reference:
            return [
                "cohort_population_invariant_mismatch:"
                f"lookback/named_roster disagree under compatibility cohort "
                f"(ref_obs={fingerprints[0][0]}, other_obs={obs_id}, "
                f"ref={reference!r}, other={fp!r})"
            ]
    return []


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


def _path_label_semantic_reasons(
    label: LearningOutcomeLabel,
    *,
    observation: LearningObservation | None,
    session_snapshot_lookup: Callable[[str], TradingSessionCalendarSnapshot | None] | None = None,
    # Deprecated alias kept for call-site migration during tests.
    session_calendar: KnownTradingSessionCalendar | None = None,
) -> list[str]:
    """Full path-label semantic matrix (schema, outcome, fingerprint, metrics, window)."""

    reasons: list[str] = []
    if label.schema_version != LEARNING_SCHEMA_VERSION:
        reasons.append(
            f"label_schema_version:{label.schema_version}!=expected:{LEARNING_SCHEMA_VERSION}"
        )

    if label.contract_id not in PATH_LABEL_CONTRACTS:
        reasons.append(f"incompatible_label_family:{label.contract_id.value}")
        return reasons

    if observation is not None:
        expected_fp = recompute_path_label_fingerprint(
            observation_id=observation.observation_id,
            observation_artifact_digest=observation.artifact_digest,
            label_contract=label.contract_id,
        )
        if label.fingerprint != expected_fp:
            reasons.append(
                f"fingerprint_mismatch:stored={label.fingerprint!r},expected={expected_fp!r}"
            )

    if label.availability is LabelAvailability.AVAILABLE:
        if label.outcome not in _ALLOWED_PATH_OUTCOMES:
            reasons.append(f"outcome_vocabulary:{label.outcome!r}")
        metrics = label.metrics if isinstance(label.metrics, Mapping) else {}
        metric_keys = set(metrics)
        missing = sorted(_AVAILABLE_METRIC_KEYS - metric_keys)
        extra = sorted(metric_keys - _AVAILABLE_METRIC_KEYS)
        if missing:
            reasons.append(f"metrics_missing_fields:{missing}")
        if extra:
            # Closed production metric surface — invented keys are corruption.
            reasons.append(f"metrics_extra_fields:{extra}")
        # Type/window checks run when required keys are present (extras still fail closed).
        if not missing:
            # Units: pct fields exact numeric (no string coercion); day indices exact int.
            for pct_key in (
                "close_return_pct",
                "max_forward_return_pct",
                "max_adverse_excursion_pct",
            ):
                raw = metrics.get(pct_key)
                if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                    reasons.append(f"metrics.{pct_key}_not_numeric:{raw!r}")
            for day_key in ("days_to_peak", "days_to_trough"):
                raw = metrics.get(day_key)
                # Production emits int day indices. Reject float (1.9), str ("1"), bool.
                if isinstance(raw, bool) or type(raw) is not int:
                    reasons.append(f"metrics.{day_key}_not_int:{raw!r}")
                    day_v = None
                else:
                    day_v = raw
                horizon_days = _PATH_LABEL_HORIZON_DAYS[label.contract_id]
                if day_v is not None and not (1 <= day_v <= horizon_days):
                    reasons.append(
                        f"metrics.{day_key}_outside_horizon:{day_v}not_in_1..{horizon_days}"
                    )
            # Entry reference: exact numeric type (int|float), never string-coerced.
            raw_entry = metrics.get("entry_reference_price")
            if isinstance(raw_entry, bool) or not isinstance(raw_entry, (int, float)):
                reasons.append(f"metrics.entry_reference_price_invalid:{raw_entry!r}")
                entry: float | None = None
            else:
                entry = float(raw_entry)
            # Exact first N market sessions after signal — proven via the
            # immutable calendar snapshot bound on the label (never latest/cache).
            signal_date = parse_canonical_session_date(metrics.get("signal_date"))
            win_start = parse_canonical_session_date(metrics.get("label_window_start"))
            win_end = parse_canonical_session_date(metrics.get("label_window_end"))
            horizon_days = _PATH_LABEL_HORIZON_DAYS[label.contract_id]
            if signal_date is None:
                reasons.append(f"metrics.signal_date_malformed:{metrics.get('signal_date')!r}")
            if win_start is None or win_end is None:
                reasons.append("metrics.label_window_dates_malformed")
            metrics_schema = metrics.get("path_label_metrics_schema_version")
            if metrics_schema != PATH_LABEL_METRICS_SCHEMA_VERSION:
                reasons.append(
                    "metrics.path_label_metrics_schema_version_invalid:"
                    f"{metrics_schema!r}!=expected:{PATH_LABEL_METRICS_SCHEMA_VERSION}"
                )
            raw_sessions = metrics.get("label_window_sessions")
            parsed_sessions: list[date] | None = None
            if not isinstance(raw_sessions, (list, tuple)):
                reasons.append(f"metrics.label_window_sessions_invalid:{raw_sessions!r}")
            else:
                parsed_sessions = []
                for item in raw_sessions:
                    session = parse_canonical_session_date(item)
                    if session is None:
                        reasons.append(f"metrics.label_window_sessions_malformed:{item!r}")
                        parsed_sessions = None
                        break
                    parsed_sessions.append(session)
                if parsed_sessions is not None:
                    if len(parsed_sessions) != horizon_days:
                        reasons.append(
                            "metrics.label_window_sessions_length:"
                            f"{len(parsed_sessions)}!=expected:{horizon_days}"
                        )
                    if len(set(parsed_sessions)) != len(parsed_sessions):
                        reasons.append("metrics.label_window_sessions_not_unique")
                    if list(parsed_sessions) != sorted(parsed_sessions):
                        reasons.append("metrics.label_window_sessions_not_sorted")
                    if (
                        win_start is not None
                        and win_end is not None
                        and parsed_sessions
                        and (parsed_sessions[0] != win_start or parsed_sessions[-1] != win_end)
                    ):
                        reasons.append("metrics.label_window_sessions_endpoint_mismatch")
            snapshot_id = metrics.get("calendar_snapshot_id")
            if not isinstance(snapshot_id, str) or not snapshot_id.strip():
                reasons.append(f"metrics.calendar_snapshot_id_invalid:{snapshot_id!r}")
                snapshot_id = None
            contract_id = metrics.get("calendar_contract_id")
            if contract_id != STOCKBIT_TRADING_SESSIONS_CONTRACT:
                reasons.append(
                    f"metrics.calendar_contract_id_invalid:{contract_id!r}"
                    f"!=expected:{STOCKBIT_TRADING_SESSIONS_CONTRACT!r}"
                )
            stored_revision = metrics.get("calendar_source_revision")
            if not isinstance(stored_revision, str) or not stored_revision.strip():
                reasons.append(f"metrics.calendar_source_revision_invalid:{stored_revision!r}")
            stored_window_digest = metrics.get("label_window_digest")
            if not isinstance(stored_window_digest, str) or not stored_window_digest.strip():
                reasons.append(f"metrics.label_window_digest_invalid:{stored_window_digest!r}")
            if win_start is not None and win_end is not None:
                if win_start > win_end:
                    reasons.append("metrics.label_window_inverted")
                if signal_date is not None and win_start <= signal_date:
                    reasons.append(
                        "metrics.label_window_not_after_signal:"
                        f"start={win_start.isoformat()},signal={signal_date.isoformat()}"
                    )
            # Load the exact snapshot bound on the label (never re-range the cache).
            snapshot: TradingSessionCalendarSnapshot | None = None
            if snapshot_id is not None:
                if session_snapshot_lookup is None:
                    reasons.append("metrics.calendar_snapshot_lookup_unproven")
                else:
                    try:
                        snapshot = session_snapshot_lookup(snapshot_id)
                    except TradingSessionCalendarSnapshotReadError as exc:
                        reasons.append(
                            f"metrics.calendar_snapshot_lookup_corrupt:{snapshot_id}:{exc}"
                        )
                        snapshot = None
                    except LearningContractError as exc:
                        reasons.append(
                            f"metrics.calendar_snapshot_lookup_corrupt:{snapshot_id}:{exc}"
                        )
                        snapshot = None
                    if snapshot is None and not any(
                        "calendar_snapshot_lookup_corrupt" in r for r in reasons
                    ):
                        reasons.append(f"metrics.calendar_snapshot_missing:{snapshot_id!r}")
                    elif snapshot is not None:
                        if snapshot.snapshot_id != snapshot_id:
                            reasons.append(
                                "metrics.calendar_snapshot_id_mismatch:"
                                f"requested={snapshot_id!r},loaded={snapshot.snapshot_id!r}"
                            )
                            snapshot = None
                        else:
                            try:
                                validate_active_stockbit_calendar_snapshot(snapshot)
                            except LearningContractError as exc:
                                reasons.append(f"metrics.calendar_snapshot_invalid:{exc}")
                                snapshot = None
            if snapshot is not None and signal_date is not None:
                if snapshot.contract_id != STOCKBIT_TRADING_SESSIONS_CONTRACT:
                    reasons.append(
                        f"metrics.calendar_snapshot_contract_invalid:{snapshot.contract_id!r}"
                    )
                if snapshot.source != TRADING_SESSION_CALENDAR_SOURCE_STOCKBIT:
                    reasons.append(f"metrics.calendar_snapshot_source_invalid:{snapshot.source!r}")
                if snapshot.benchmark != TRADING_SESSION_CALENDAR_BENCHMARK_IHSG:
                    reasons.append(
                        f"metrics.calendar_snapshot_benchmark_invalid:{snapshot.benchmark!r}"
                    )
                if (
                    isinstance(stored_revision, str)
                    and stored_revision.strip()
                    and stored_revision != snapshot.source_revision
                ):
                    reasons.append(
                        "metrics.calendar_source_revision_mismatch:"
                        f"stored={stored_revision!r},"
                        f"snapshot={snapshot.source_revision!r}"
                    )
                expected = snapshot.first_n_sessions_after(signal_date, horizon_days)
                if expected is None:
                    reasons.append(
                        "metrics.label_window_sessions_unproven:"
                        f"signal={signal_date.isoformat()},n={horizon_days}"
                    )
                else:
                    if win_start is not None and win_end is not None:
                        if win_start != expected[0] or win_end != expected[-1]:
                            reasons.append(
                                "metrics.label_window_not_first_n_sessions:"
                                f"got={win_start.isoformat()}..{win_end.isoformat()},"
                                f"expected={expected[0].isoformat()}.."
                                f"{expected[-1].isoformat()},n={horizon_days}"
                            )
                    if parsed_sessions is not None and tuple(parsed_sessions) != expected:
                        reasons.append("metrics.label_window_sessions_not_first_n")
                    expected_window_digest = label_window_digest(
                        calendar_snapshot_id=snapshot.snapshot_id,
                        label_contract_id=label.contract_id.value,
                        signal_date=signal_date,
                        sessions=expected,
                    )
                    if (
                        isinstance(stored_window_digest, str)
                        and stored_window_digest != expected_window_digest
                    ):
                        reasons.append(
                            "metrics.label_window_digest_mismatch:"
                            f"stored={stored_window_digest!r},"
                            f"expected={expected_window_digest!r}"
                        )
            # Legacy session_calendar param no longer grants authority without snapshot.
            del session_calendar
            if observation is not None:
                obs_session = observation_session_date(observation)
                if (
                    signal_date is not None
                    and obs_session is not None
                    and signal_date != obs_session
                ):
                    reasons.append(
                        "metrics.signal_date_session_mismatch:"
                        f"signal={signal_date.isoformat()},session={obs_session.isoformat()}"
                    )
                # metrics.ticker must equal parent observation ticker (case-normalized).
                # Presence alone is not authority — BBCA obs + TLKM metrics is corruption.
                obs_ticker = _parent_observation_ticker(observation)
                raw_metric_ticker = metrics.get("ticker")
                if not isinstance(raw_metric_ticker, str) or not raw_metric_ticker.strip():
                    # Missing key already reported via metrics_missing_fields; invalid
                    # non-string / blank values fail closed here when key is present.
                    if "ticker" in metrics:
                        reasons.append(f"metrics.ticker_invalid:{raw_metric_ticker!r}")
                elif obs_ticker is not None:
                    metric_ticker = raw_metric_ticker.strip().upper()
                    if metric_ticker != obs_ticker:
                        reasons.append(
                            "metrics.ticker_mismatch:"
                            f"metrics={metric_ticker},observation={obs_ticker}"
                        )
                # Entry reference equals frozen shared.current_price (when entry typed).
                # Label entry must already be exact numeric; frozen is observation truth.
                if entry is not None:
                    payload = observation.decision_payload
                    shared = payload.get("shared") if isinstance(payload, Mapping) else None
                    raw_price = shared.get("current_price") if isinstance(shared, Mapping) else None
                    try:
                        frozen = float(raw_price) if raw_price is not None else None
                    except (TypeError, ValueError):
                        frozen = None
                    if frozen is None or frozen <= 0:
                        reasons.append(f"entry_reference_no_frozen_price:{raw_price!r}")
                    elif abs(entry - frozen) > 1e-9:
                        reasons.append(f"entry_reference_mismatch:entry={entry},frozen={frozen}")
    elif label.availability is LabelAvailability.UNAVAILABLE:
        metrics = label.metrics if isinstance(label.metrics, Mapping) else {}
        reason = metrics.get("unavailable_reason")
        if not isinstance(reason, str) or not reason.strip():
            reasons.append("metrics.unavailable_reason_missing")
        elif reason.strip() not in _SUPPORTED_PATH_UNAVAILABLE_REASONS:
            # Closed production vocabulary — invented non-empty strings are corruption.
            reasons.append(f"metrics.unavailable_reason_unsupported:{reason.strip()!r}")

    return reasons


def _parent_observation_ticker(observation: LearningObservation) -> str | None:
    """Authoritative observation ticker (window/payload bound), case-normalized."""
    bound = bound_economic_session(observation)
    if bound is not None:
        return bound[0]
    payload = observation.decision_payload
    if isinstance(payload, Mapping):
        raw = payload.get("ticker")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().upper()
    window = parse_window_id(observation.window_id)
    if window is not None:
        return window[0]
    return None


def count_labels_by_horizon(
    *,
    observation_ids: Sequence[str],
    labels: Sequence[LearningOutcomeLabel],
    observations_by_id: Mapping[str, LearningObservation] | None = None,
    session_snapshot_lookup: Callable[[str], TradingSessionCalendarSnapshot | None] | None = None,
    session_calendar: KnownTradingSessionCalendar | None = None,
) -> LabelCohortValidation:
    """Count path labels after digest, identity, basis, and full semantic checks.

    Read-side authority: a rehashed ``AVAILABLE``+``outcome=None`` (or
    ``UNAVAILABLE``+outcome) label is integrity corruption — never counted as a
    normal available/unavailable success and never alone enables
    ``CHALLENGE_INPUT_READY``.

    Multi-row path labels for the same observation + horizon are also
    authority-bearing integrity corruption (``conflict``): they skip AVAILABLE
    tally and set ``has_integrity_corruption`` so classification fails closed.

    Incompatible label families (e.g. pre-open on an accumulation observation)
    fail closed rather than being silently ignored.

    ``session_snapshot_lookup`` loads the exact immutable calendar snapshot
    bound on each AVAILABLE label by ``calendar_snapshot_id``. Absence fails closed.
    """
    del session_calendar  # no longer authoritative
    obs_set = set(observation_ids)
    obs_map = dict(observations_by_id or {})
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

        parent = obs_map.get(label.observation_id)
        if label.contract_id not in PATH_LABEL_CONTRACTS:
            # Incompatible family attached to an accumulation observation → corruption.
            label_reasons.append(f"incompatible_label_family:{label.contract_id.value}")
        else:
            label_reasons.extend(
                _path_label_semantic_reasons(
                    label,
                    observation=parent,
                    session_snapshot_lookup=session_snapshot_lookup,
                )
            )

        if label_reasons:
            invalid_label_count += 1
            invalid_reasons.append(f"{label.label_id}:{','.join(label_reasons)}")
            continue
        if label.contract_id in by_contract:
            by_contract[label.contract_id].append(label)

    # Track any supported-contract terminal presence (valid or invalid) per
    # horizon so malformed H10 rows are invalid-only, never also insufficient.
    terminal_presence: dict[LearningContractId, set[str]] = {c: set() for c in PATH_LABEL_CONTRACTS}
    for label in labels:
        if label.observation_id not in obs_set:
            continue
        if label.contract_id in PATH_LABEL_CONTRACTS:
            terminal_presence[label.contract_id].add(label.observation_id)

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
        for obs_id, group in by_obs.items():
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
        # Insufficient = validated obs with no supported-contract terminal row
        # (valid or invalid). Malformed supported rows already occupy presence.
        insufficient = max(0, len(obs_set) - len(terminal_presence[contract]))
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
    session_snapshot_lookup: Callable[[str], TradingSessionCalendarSnapshot | None] | None = None,
    session_calendar: KnownTradingSessionCalendar | None = None,
) -> CohortProducerReadiness:
    """Project one cohort's producer readiness from already-loaded artifacts.

    ``session_snapshot_lookup`` loads each label's bound immutable calendar
    snapshot by ID. Without it, AVAILABLE windows fail closed.
    """
    del session_calendar
    obs_validation = validate_observation_cohort(
        observations,
        purpose_value=purpose_value,
        compatibility_id=compatibility_id,
        expected_learning_observation_contract_id=expected_learning_observation_contract_id,
        expected_producer_observation_contract=expected_producer_observation_contract,
    )

    # Invalid / authority-corrupt rows contribute zero Action, readiness, or labels.
    # Use full matrix validation success only — never purpose/compat presence alone,
    # and never expand to all loaded IDs when the cohort is corrupted.
    validated_id_set = frozenset(obs_validation.validated_observation_ids)
    validated_observations = [o for o in observations if o.observation_id in validated_id_set]

    action_counts: Counter[str] = Counter()
    readiness_states: Counter[str] = Counter()
    readiness_present = 0
    readiness_missing = 0

    for obs in validated_observations:
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
    observations_by_id = {o.observation_id: o for o in observations}
    # Label tallies follow the same validated-ID set as Action/readiness.
    label_ids = list(obs_validation.validated_observation_ids)

    label_validation = count_labels_by_horizon(
        observation_ids=label_ids,
        labels=labels,
        observations_by_id=observations_by_id,
        session_snapshot_lookup=session_snapshot_lookup,
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
