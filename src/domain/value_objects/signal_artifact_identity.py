"""Immutable artifact-identity, compatibility, and provenance value objects.

Layer: Domain (pure value objects, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import re
from typing import Any


_SHA256_PREFIXED = re.compile(r"^sha256:[0-9a-f]{64}\Z")
_LOWERCASE_HEX_64 = re.compile(r"^[0-9a-f]{64}\Z")
_LOWERCASE_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
_UPPERCASE_TICKER = re.compile(r"^[A-Z][A-Z0-9]*$")


def _fail(value: Any, field: str, msg: str) -> None:
    raise ValueError(f"{field}: {msg}, got {value!r}")


def _require_sha256_prefixed(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_PREFIXED.match(value):
        _fail(value, field, "must be 'sha256:' followed by exactly 64 lowercase hex characters")


def _require_lowercase_hex_64(value: str, field: str) -> None:
    if not isinstance(value, str) or not _LOWERCASE_HEX_64.match(value):
        _fail(value, field, "must be exactly 64 lowercase hex characters")


def _require_non_empty_trimmed(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        _fail(value, field, "must be a non-empty trimmed string")
    if value != value.strip():
        _fail(value, field, "must not have surrounding whitespace")


def _require_lowercase_snake(value: str, field: str) -> None:
    _require_non_empty_trimmed(value, field)
    if not _LOWERCASE_SNAKE.match(value):
        _fail(value, field, "must be lowercase snake_case")


def _require_ticker(value: str) -> None:
    _require_non_empty_trimmed(value, "ticker")
    if not _UPPERCASE_TICKER.match(value):
        _fail(value, "ticker", "must be uppercase")


def _require_positive_int_or_none(value: Any, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(value, field, f"must be a positive integer or None, not {type(value).__name__}")
    if value < 1:
        _fail(value, field, "must be a positive integer")


def _require_tz_aware(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, datetime):
        _fail(value, field, f"must be a datetime, not {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        _fail(value, field, "must be timezone-aware")


def _require_at_least_one_present(a: Any, a_name: str, b: Any, b_name: str) -> None:
    if a is None and b is None:
        raise ValueError(
            f"at least one of {a_name} or {b_name} must be present"
        )


def _require_instance(value: object, expected_type: type, field: str) -> None:
    if not isinstance(value, expected_type):
        _fail(value, field, f"must be {expected_type.__name__}, not {type(value).__name__}")


def _require_exact_date(value: object, field: str) -> None:
    """Require value is a date or None. datetime is rejected (subclass)."""
    if value is None:
        return
    if not isinstance(value, date):
        _fail(value, field, f"must be a date, not {type(value).__name__}")
    if isinstance(value, datetime):
        _fail(value, field, "must be a date, not datetime")


def _require_required_exact_date(value: object, field: str) -> None:
    """Require value is a date and never None."""
    if value is None:
        raise ValueError(f"{field}: must be a date, not None")
    _require_exact_date(value, field)


def _require_required_tz_aware(value: object, field: str) -> None:
    """Require value is a timezone-aware datetime and never None."""
    if value is None:
        raise ValueError(f"{field}: must be a datetime, not None")
    if not isinstance(value, datetime):
        _fail(value, field, f"must be a datetime, not {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        _fail(value, field, "must be timezone-aware")


# ---------------------------------------------------------------------------
# Final hash wrappers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactId:
    """Wraps a captured-artifact hash identity: sha256:<64 lowercase hex>."""

    value: str

    def __post_init__(self) -> None:
        _require_sha256_prefixed(self.value, "ArtifactId.value")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SemanticCompatibilityId:
    """Wraps a learning/readiness cohort hash identity: sha256:<64 lowercase hex>."""

    value: str

    def __post_init__(self) -> None:
        _require_sha256_prefixed(self.value, "SemanticCompatibilityId.value")

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Semantic compatibility dimensions — decides whether artifacts may be pooled
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SemanticCompatibilityDimensions:
    """Dimensions whose change can alter meaning or calculation of evidence/outcomes."""

    observation_contract: str
    setup_family: str | None
    evidence_contract_version: str
    observation_schema_version: int | None
    label_schema_version: int | None
    semantic_engine_version: str
    material_config_hash: str
    authority_registrations_hash: str
    execution_label_policy_version: str | None

    def __post_init__(self) -> None:
        _require_non_empty_trimmed(self.observation_contract, "observation_contract")
        if self.setup_family is not None:
            _require_lowercase_snake(self.setup_family, "setup_family")
        _require_non_empty_trimmed(self.evidence_contract_version, "evidence_contract_version")
        _require_positive_int_or_none(self.observation_schema_version, "observation_schema_version")
        _require_positive_int_or_none(self.label_schema_version, "label_schema_version")
        _require_at_least_one_present(
            self.observation_schema_version, "observation_schema_version",
            self.label_schema_version, "label_schema_version",
        )
        _require_non_empty_trimmed(self.semantic_engine_version, "semantic_engine_version")
        _require_lowercase_hex_64(self.material_config_hash, "material_config_hash")
        _require_lowercase_hex_64(
            self.authority_registrations_hash, "authority_registrations_hash",
        )
        if self.execution_label_policy_version is not None:
            _require_non_empty_trimmed(
                self.execution_label_policy_version, "execution_label_policy_version",
            )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "authority_registrations_hash": self.authority_registrations_hash,
            "evidence_contract_version": self.evidence_contract_version,
            "execution_label_policy_version": self.execution_label_policy_version,
            "label_schema_version": self.label_schema_version,
            "material_config_hash": self.material_config_hash,
            "observation_contract": self.observation_contract,
            "observation_schema_version": self.observation_schema_version,
            "semantic_engine_version": self.semantic_engine_version,
            "setup_family": self.setup_family,
        }

    def to_canonical_json(self) -> str:
        return _canonical_json(self.to_canonical_dict())


# ---------------------------------------------------------------------------
# Artifact uniqueness dimensions — per-capture identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactIdentityDimensions:
    """Dimensions that uniquely identify one captured artifact."""

    artifact_type: str
    semantic_compatibility_id: SemanticCompatibilityId
    effective_session: date
    ticker: str
    universe_snapshot_id: str
    source_snapshot_cutoff_id: str

    def __post_init__(self) -> None:
        _require_lowercase_snake(self.artifact_type, "artifact_type")
        _require_instance(
            self.semantic_compatibility_id, SemanticCompatibilityId,
            "semantic_compatibility_id",
        )
        _require_required_exact_date(self.effective_session, "effective_session")
        _require_ticker(self.ticker)
        _require_non_empty_trimmed(self.universe_snapshot_id, "universe_snapshot_id")
        _require_non_empty_trimmed(
            self.source_snapshot_cutoff_id, "source_snapshot_cutoff_id",
        )

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "artifact_type": self.artifact_type,
            "effective_session": _serialize_date(self.effective_session),
            "semantic_compatibility_id": self.semantic_compatibility_id.value,
            "source_snapshot_cutoff_id": self.source_snapshot_cutoff_id,
            "ticker": self.ticker,
            "universe_snapshot_id": self.universe_snapshot_id,
        }

    def to_canonical_json(self) -> str:
        return _canonical_json(self.to_canonical_dict())


# ---------------------------------------------------------------------------
# Typed source provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactSourceProvenance:
    """Provenance for one source/data-family within a complete artifact."""

    source_family: str
    provider: str
    source_snapshot_id: str | None
    observed_through: date | None
    available_at: datetime | None
    cutoff_at: datetime | None

    def __post_init__(self) -> None:
        _require_lowercase_snake(self.source_family, "source_family")
        _require_lowercase_snake(self.provider, "provider")
        if self.source_snapshot_id is not None:
            _require_non_empty_trimmed(self.source_snapshot_id, "source_snapshot_id")
        _require_exact_date(self.observed_through, "observed_through")
        _require_tz_aware(self.available_at, "available_at")
        _require_tz_aware(self.cutoff_at, "cutoff_at")

    def _sort_key(self) -> tuple:
        return (self.source_family, self.provider, self.source_snapshot_id or "")

    def to_canonical_dict(self) -> dict[str, object]:
        return {
            "available_at": _serialize_datetime_opt(self.available_at),
            "cutoff_at": _serialize_datetime_opt(self.cutoff_at),
            "observed_through": _serialize_date_opt(self.observed_through),
            "provider": self.provider,
            "source_family": self.source_family,
            "source_snapshot_id": self.source_snapshot_id,
        }

    def to_canonical_json(self) -> str:
        return _canonical_json(self.to_canonical_dict())


# ---------------------------------------------------------------------------
# Complete artifact provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactProvenance:
    """Complete audit trail for one captured artifact."""

    application_revision: str
    complete_config_hash: str
    complete_authority_registry_hash: str
    universe_snapshot_id: str
    idx_calendar_version: str
    session_rule_version: str
    decision_at: datetime
    captured_at: datetime
    latest_completed_session: date
    analysis_as_of: date
    sources: tuple[ArtifactSourceProvenance, ...]
    invocation_command: str | None = None
    invocation_actor: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_trimmed(self.application_revision, "application_revision")
        _require_lowercase_hex_64(self.complete_config_hash, "complete_config_hash")
        _require_lowercase_hex_64(
            self.complete_authority_registry_hash, "complete_authority_registry_hash",
        )
        _require_non_empty_trimmed(self.universe_snapshot_id, "universe_snapshot_id")
        _require_non_empty_trimmed(self.idx_calendar_version, "idx_calendar_version")
        _require_non_empty_trimmed(self.session_rule_version, "session_rule_version")
        _require_required_tz_aware(self.decision_at, "decision_at")
        _require_required_tz_aware(self.captured_at, "captured_at")
        _require_required_exact_date(self.latest_completed_session, "latest_completed_session")
        _require_required_exact_date(self.analysis_as_of, "analysis_as_of")
        if self.latest_completed_session > self.analysis_as_of:
            raise ValueError(
                f"latest_completed_session ({self.latest_completed_session}) "
                f"must not be after analysis_as_of ({self.analysis_as_of})"
            )
        if not isinstance(self.sources, tuple):
            raise ValueError("sources must be a tuple")
        for i, s in enumerate(self.sources):
            if not isinstance(s, ArtifactSourceProvenance):
                raise ValueError(
                    f"sources[{i}] must be ArtifactSourceProvenance, "
                    f"got {type(s).__name__}"
                )
        if self.invocation_command is not None:
            _require_non_empty_trimmed(self.invocation_command, "invocation_command")
        if self.invocation_actor is not None:
            _require_non_empty_trimmed(self.invocation_actor, "invocation_actor")
        _check_duplicate_sources(self.sources)

    def to_canonical_dict(self) -> dict[str, object]:
        sorted_sources = sorted(self.sources, key=lambda s: s._sort_key())
        return {
            "analysis_as_of": _serialize_date(self.analysis_as_of),
            "application_revision": self.application_revision,
            "captured_at": _serialize_datetime(self.captured_at),
            "complete_authority_registry_hash": self.complete_authority_registry_hash,
            "complete_config_hash": self.complete_config_hash,
            "decision_at": _serialize_datetime(self.decision_at),
            "idx_calendar_version": self.idx_calendar_version,
            "invocation_actor": self.invocation_actor,
            "invocation_command": self.invocation_command,
            "latest_completed_session": _serialize_date(self.latest_completed_session),
            "session_rule_version": self.session_rule_version,
            "sources": [s.to_canonical_dict() for s in sorted_sources],
            "universe_snapshot_id": self.universe_snapshot_id,
        }

    def to_canonical_json(self) -> str:
        return _canonical_json(self.to_canonical_dict())


def _check_duplicate_sources(sources: tuple[ArtifactSourceProvenance, ...]) -> None:
    seen = set()
    for s in sources:
        key = (s.source_family, s.provider, s.source_snapshot_id)
        if key in seen:
            raise ValueError(
                f"duplicate source provenance entry: "
                f"source_family={s.source_family!r}, provider={s.provider!r}, "
                f"source_snapshot_id={s.source_snapshot_id!r}"
            )
        seen.add(key)


# ---------------------------------------------------------------------------
# Resolved identity bundle
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalArtifactIdentity:
    """Binds resolved IDs to provenance. Does not perform hashing."""

    artifact_id: ArtifactId
    semantic_compatibility_id: SemanticCompatibilityId
    provenance: ArtifactProvenance

    def __post_init__(self) -> None:
        _require_instance(self.artifact_id, ArtifactId, "artifact_id")
        _require_instance(
            self.semantic_compatibility_id, SemanticCompatibilityId,
            "semantic_compatibility_id",
        )
        _require_instance(self.provenance, ArtifactProvenance, "provenance")


# ---------------------------------------------------------------------------
# Canonical serialization helpers
# ---------------------------------------------------------------------------


def _serialize_date(d: date) -> str:
    return d.isoformat()


def _serialize_date_opt(d: date | None) -> str | None:
    return None if d is None else d.isoformat()


def _serialize_datetime(dt: datetime) -> str:
    utc = dt.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _serialize_datetime_opt(dt: datetime | None) -> str | None:
    return None if dt is None else _serialize_datetime(dt)


def _canonical_json(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
