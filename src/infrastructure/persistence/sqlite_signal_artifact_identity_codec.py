"""Strict SQLite codec for SignalArtifactIdentity serialization.

Layer: Infrastructure
"""

from __future__ import annotations

import json
from datetime import date, datetime

from src.domain.value_objects.signal_artifact_identity import (
    ArtifactId,
    ArtifactProvenance,
    ArtifactSourceProvenance,
    SemanticCompatibilityId,
    SignalArtifactIdentity,
)

_PROVENANCE_KEYS = frozenset(
    {
        "analysis_as_of",
        "application_revision",
        "captured_at",
        "complete_authority_registry_hash",
        "complete_config_hash",
        "decision_at",
        "idx_calendar_version",
        "invocation_actor",
        "invocation_command",
        "latest_completed_session",
        "session_rule_version",
        "sources",
        "universe_snapshot_id",
    }
)

_SOURCE_KEYS = frozenset(
    {
        "available_at",
        "cutoff_at",
        "observed_through",
        "provider",
        "source_family",
        "source_snapshot_id",
    }
)


def encode_signal_artifact_identity(
    identity: SignalArtifactIdentity | None,
) -> tuple[str, str, str]:
    if identity is None:
        return ("", "", "")
    if not isinstance(identity, SignalArtifactIdentity):
        raise TypeError(f"Expected SignalArtifactIdentity | None, got {type(identity).__name__}")
    return (
        str(identity.artifact_id),
        str(identity.semantic_compatibility_id),
        identity.provenance.to_canonical_json(),
    )


def decode_signal_artifact_identity(
    *,
    artifact_id_raw: object,
    semantic_compatibility_id_raw: object,
    provenance_json_raw: object,
) -> SignalArtifactIdentity | None:
    _require_str(artifact_id_raw, "artifact_id")
    _require_str(semantic_compatibility_id_raw, "semantic_compatibility_id")
    _require_str(provenance_json_raw, "artifact_provenance_json")

    if not artifact_id_raw and not semantic_compatibility_id_raw and not provenance_json_raw:
        return None

    if not artifact_id_raw or not semantic_compatibility_id_raw or not provenance_json_raw:
        raise ValueError(
            "Partial signal artifact identity: all three columns must be empty or "
            "all three must be non-empty"
        )

    artifact_id = _decode_artifact_id(artifact_id_raw)
    sem_compat_id = _decode_semantic_compatibility_id(semantic_compatibility_id_raw)
    provenance = _decode_provenance(provenance_json_raw)

    return SignalArtifactIdentity(
        artifact_id=artifact_id,
        semantic_compatibility_id=sem_compat_id,
        provenance=provenance,
    )


def _require_str(value: object, field: str) -> None:
    if value is None:
        raise ValueError(
            f"{field} is NULL: database column is NOT NULL — "
            "empty string expected for absent identity"
        )
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, got {type(value).__name__}")


def _decode_artifact_id(raw: str) -> ArtifactId:
    try:
        return ArtifactId(raw)
    except ValueError as e:
        raise ValueError(f"artifact_id: {e}") from e


def _decode_semantic_compatibility_id(raw: str) -> SemanticCompatibilityId:
    try:
        return SemanticCompatibilityId(raw)
    except ValueError as e:
        raise ValueError(f"semantic_compatibility_id: {e}") from e


def _decode_provenance(raw: str) -> ArtifactProvenance:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"artifact_provenance_json: malformed JSON — {e}") from e

    if not isinstance(data, dict):
        raise ValueError(
            f"artifact_provenance_json: must be a JSON object, got {type(data).__name__}"
        )

    actual_keys = frozenset(data.keys())
    if actual_keys != _PROVENANCE_KEYS:
        missing = _PROVENANCE_KEYS - actual_keys
        extra = actual_keys - _PROVENANCE_KEYS
        parts = []
        if missing:
            parts.append(f"missing keys: {sorted(missing)}")
        if extra:
            parts.append(f"unexpected keys: {sorted(extra)}")
        raise ValueError("artifact_provenance_json: " + "; ".join(parts))

    sources_raw = data["sources"]
    if not isinstance(sources_raw, list):
        raise ValueError(
            f"artifact_provenance_json.sources: must be a list, got {type(sources_raw).__name__}"
        )

    sources = [_decode_source(i, s) for i, s in enumerate(sources_raw)]
    _check_duplicate_sources(sources)

    provenance = ArtifactProvenance(
        application_revision=_require_str_field(data, "application_revision"),
        complete_config_hash=_require_str_field(data, "complete_config_hash"),
        complete_authority_registry_hash=_require_str_field(
            data, "complete_authority_registry_hash"
        ),
        universe_snapshot_id=_require_str_field(data, "universe_snapshot_id"),
        idx_calendar_version=_require_str_field(data, "idx_calendar_version"),
        session_rule_version=_require_str_field(data, "session_rule_version"),
        decision_at=_decode_utc_datetime(data["decision_at"], "decision_at"),
        captured_at=_decode_utc_datetime(data["captured_at"], "captured_at"),
        latest_completed_session=_decode_date(
            data["latest_completed_session"], "latest_completed_session"
        ),
        analysis_as_of=_decode_date(data["analysis_as_of"], "analysis_as_of"),
        sources=tuple(sources),
        invocation_command=_decode_optional_str(data.get("invocation_command")),
        invocation_actor=_decode_optional_str(data.get("invocation_actor")),
    )

    canonical = provenance.to_canonical_json()
    if raw != canonical:
        raise ValueError("artifact_provenance_json must use canonical provenance serialization")

    return provenance


def _decode_source(index: int, raw: object) -> ArtifactSourceProvenance:
    if not isinstance(raw, dict):
        raise ValueError(
            f"artifact_provenance_json.sources[{index}]: must be a JSON object, "
            f"got {type(raw).__name__}"
        )
    actual_keys = frozenset(raw.keys())
    if actual_keys != _SOURCE_KEYS:
        missing = _SOURCE_KEYS - actual_keys
        extra = actual_keys - _SOURCE_KEYS
        parts = []
        if missing:
            parts.append(f"missing keys: {sorted(missing)}")
        if extra:
            parts.append(f"unexpected keys: {sorted(extra)}")
        raise ValueError(f"artifact_provenance_json.sources[{index}]: " + "; ".join(parts))

    return ArtifactSourceProvenance(
        source_family=_require_str_field(raw, "source_family"),
        provider=_require_str_field(raw, "provider"),
        source_snapshot_id=_decode_optional_str(raw.get("source_snapshot_id")),
        observed_through=_decode_optional_date(
            raw.get("observed_through"), f"sources[{index}].observed_through"
        ),
        available_at=_decode_optional_utc_datetime(
            raw.get("available_at"), f"sources[{index}].available_at"
        ),
        cutoff_at=_decode_optional_utc_datetime(
            raw.get("cutoff_at"), f"sources[{index}].cutoff_at"
        ),
    )


def _check_duplicate_sources(sources: list[ArtifactSourceProvenance]) -> None:
    seen = set()
    for s in sources:
        key = (s.source_family, s.provider, s.source_snapshot_id)
        if key in seen:
            raise ValueError(
                f"Duplicate source provenance entry: "
                f"source_family={s.source_family!r}, "
                f"provider={s.provider!r}, "
                f"source_snapshot_id={s.source_snapshot_id!r}"
            )
        seen.add(key)


def _require_str_field(data: dict[str, object], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(
            f"artifact_provenance_json.{key}: must be a string, got {type(value).__name__}"
        )
    return value


def _decode_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Expected string or null, got {type(value).__name__}")
    return value


def _decode_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(
            f"artifact_provenance_json.{field}: must be a string, got {type(value).__name__}"
        )
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError) as e:
        raise ValueError(f"artifact_provenance_json.{field}: invalid date {value!r} — {e}") from e


def _decode_optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    return _decode_date(value, field)


def _decode_utc_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(
            f"artifact_provenance_json.{field}: must be a string, got {type(value).__name__}"
        )
    if not value.endswith("Z"):
        raise ValueError(
            f"artifact_provenance_json.{field}: must end with 'Z' "
            f"(UTC canonical format), got {value!r}"
        )
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        raise ValueError(
            f"artifact_provenance_json.{field}: invalid datetime {value!r} — {e}"
        ) from e
    return dt


def _decode_optional_utc_datetime(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    return _decode_utc_datetime(value, field)
