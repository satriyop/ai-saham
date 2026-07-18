"""Canonical persisted-artifact schema version constants.

Layer: Domain
Depends on: stdlib only

These are the single source of truth for candidate-observation and
forward-label schema identity. Do not hardcode another canonical 2, 3, or 4
anywhere else — import these constants instead.

v3 -> v4 (SECTOR-CONTEXT-IDENTITY): the Alpha/Trigger sector evidence identity
`market_context` was removed; the SectorContextEvidence producer emits
`sector_context`. Older schema (1-3) rows are outside the current canonical
contract — they are never mutated, migrated, or reinterpreted here, and their
raw payloads are not validated by the current-contract validator below.
"""

from __future__ import annotations

from src.domain.value_objects.alpha_trigger_score import (
    REMOVED_MARKET_CONTEXT_EVIDENCE_NAME,
    SECTOR_CONTEXT_EVIDENCE_NAME,
)

CANDIDATE_OBSERVATION_SCHEMA_VERSION = 4
SIGNAL_FORWARD_LABEL_SCHEMA_VERSION = 2


def validate_route_metadata_identity(
    alpha_trigger_route_metadata: object,
    *,
    context: str = "canonical artifact",
) -> None:
    """Schema-independent Alpha/Trigger route-metadata identity validation.

    Applies to any artifact already known to be a *current canonical* artifact
    (a schema-4 observation or a current-schema forward label), regardless of
    which schema-version constant labels it. The metadata must be either None or
    a list/tuple of dicts, and every dict must carry a non-empty string
    ``group``. The removed ``market_context`` identity raises; ``sector_context``
    and other current group identities pass. Malformed metadata raises rather
    than being silently discarded — the value is never rewritten or mapped.

    ``context`` is a caller-supplied prefix for error messages so each boundary
    (observation schema, forward label, repository) reports its own identity.
    """
    if alpha_trigger_route_metadata is None:
        return
    if not isinstance(alpha_trigger_route_metadata, (list, tuple)):
        raise ValueError(
            f"{context} alpha_trigger_route_metadata must be None or a "
            f"list/tuple of dicts, got {type(alpha_trigger_route_metadata).__name__}"
        )
    for entry in alpha_trigger_route_metadata:
        if not isinstance(entry, dict):
            raise ValueError(
                f"{context} alpha_trigger_route_metadata entries must be dicts, "
                f"got {type(entry).__name__}"
            )
        group = entry.get("group")
        if not isinstance(group, str) or group == "":
            raise ValueError(
                f"{context} alpha_trigger_route_metadata entries must have a "
                "non-empty string 'group'"
            )
        if group == REMOVED_MARKET_CONTEXT_EVIDENCE_NAME:
            raise ValueError(
                f"{context} cannot contain removed Alpha/Trigger group "
                f"{REMOVED_MARKET_CONTEXT_EVIDENCE_NAME!r}; use "
                f"{SECTOR_CONTEXT_EVIDENCE_NAME!r}"
            )


def validate_current_alpha_trigger_identity(
    *,
    schema_version: int,
    alpha_trigger_route_metadata: object,
) -> None:
    """Validate Alpha/Trigger route-metadata identity for the current
    candidate-observation schema.

    Only the current candidate-observation schema
    (CANDIDATE_OBSERVATION_SCHEMA_VERSION) is interpreted. Any other
    schema_version returns immediately without inspecting the payload — older
    rows are outside the current canonical contract and are neither validated
    nor reinterpreted here. For the current schema, delegates to the
    schema-independent :func:`validate_route_metadata_identity`.
    """
    if schema_version != CANDIDATE_OBSERVATION_SCHEMA_VERSION:
        return
    validate_route_metadata_identity(
        alpha_trigger_route_metadata,
        context=f"schema_version={CANDIDATE_OBSERVATION_SCHEMA_VERSION}",
    )
