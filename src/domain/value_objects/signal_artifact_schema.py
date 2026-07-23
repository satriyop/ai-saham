"""Canonical persisted-artifact schema version constants.

Layer: Domain
Depends on: stdlib only

These are the single source of truth for candidate-observation and
forward-label schema identity. Do not hardcode another canonical 2, 3, 4, or 5
anywhere else — import these constants instead.

v3 -> v4 (SECTOR-CONTEXT-IDENTITY): the Alpha/Trigger sector evidence identity
`market_context` was removed; the SectorContextEvidence producer emits
`sector_context`.

v4 -> v5 (DQ-001): missing-vs-zero flow component semantics and
flow_component_coverage / flow_missing_components fingerprint fields.
v5 -> v6 (capture DecisionPolicy wiring): screen/backfill pass market_context
into DecisionPolicy and wire source-availability assessment on historical
capture so decision_constraints.regime and signal_authority_coverage reflect
runtime policy inputs rather than RISK_ON/0.0 defaults.
v6 -> v7 (discovery authority + settled bandar): screen/discovery uses
ATTACHED_REQUIRED authority denominator scope (intentionally unattached
setup does not dilute flow-only coverage); flow source authority uses
settled_authority_fraction so unassessed bandar blocks complete-authority
claims without zeroing CURRENT broker settlement.
v7 -> v8 (named setup match persistence): discovery observations persist
lean per-setup MATCH/PARTIAL/NO_MATCH + failed_gates (+ match_strength,
family, entry_authority) under sub_signal_fingerprint.named_setup_evaluations.
Diagnostic/research only — does not change ENTER/authority scoring.
Older schema (1-7) rows are outside the current canonical contract — they are
never mutated, migrated, or reinterpreted here, and their raw payloads are not
validated by the current-contract validator below.
"""

from __future__ import annotations

from src.domain.value_objects.alpha_trigger_score import (
    REMOVED_MARKET_CONTEXT_EVIDENCE_NAME,
    SECTOR_CONTEXT_EVIDENCE_NAME,
)
from src.domain.value_objects.foreign_flow_score_breakdown import (
    INSTITUTIONAL_FLOW_COMPONENT_KEYS,
)

CANDIDATE_OBSERVATION_SCHEMA_VERSION = 8
SIGNAL_FORWARD_LABEL_SCHEMA_VERSION = 3


def validate_route_metadata_identity(
    alpha_trigger_route_metadata: object,
    *,
    context: str = "canonical artifact",
) -> None:
    """Schema-independent Alpha/Trigger route-metadata identity validation.

    Applies to any artifact already known to be a *current canonical* artifact
    (a current-schema observation or a current-schema forward label), regardless
    of which schema-version constant labels it. The metadata must be either None
    or a list/tuple of dicts, and every dict must carry a non-empty string
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


def validate_flow_component_fingerprint(
    *,
    component_coverage: object,
    missing_components: object,
    context: str,
) -> None:
    """Validate DQ-001 flow completeness without normalizing malformed data."""
    if missing_components is None:
        missing: tuple[object, ...] = ()
    elif isinstance(missing_components, (list, tuple)):
        missing = tuple(missing_components)
    else:
        raise ValueError(f"{context} flow_missing_components must be a list/tuple")

    if component_coverage is None:
        if missing:
            raise ValueError(
                f"{context} cannot name missing flow components without coverage"
            )
        return
    if isinstance(component_coverage, bool) or not isinstance(
        component_coverage, (int, float)
    ):
        raise ValueError(f"{context} flow_component_coverage must be numeric or None")
    coverage = float(component_coverage)
    if not 0.0 <= coverage <= 1.0:
        raise ValueError(f"{context} flow_component_coverage must be in [0, 1]")
    if any(not isinstance(key, str) for key in missing):
        raise ValueError(f"{context} flow_missing_components entries must be strings")
    if len(missing) != len(set(missing)):
        raise ValueError(f"{context} flow_missing_components must be unique")
    unexpected = sorted(set(missing) - INSTITUTIONAL_FLOW_COMPONENT_KEYS)
    if unexpected:
        raise ValueError(
            f"{context} has unknown flow_missing_components: {unexpected}"
        )
    if missing and coverage >= 1.0:
        raise ValueError(
            f"{context} cannot have full flow coverage with missing components"
        )


def validate_current_flow_component_fingerprint(
    *,
    schema_version: int,
    fingerprint: object,
) -> None:
    if schema_version != CANDIDATE_OBSERVATION_SCHEMA_VERSION:
        return
    if not isinstance(fingerprint, dict):
        raise ValueError(
            f"schema_version={schema_version} sub_signal_fingerprint must be a dict"
        )
    validate_flow_component_fingerprint(
        component_coverage=fingerprint.get("flow_component_coverage"),
        missing_components=fingerprint.get("flow_missing_components"),
        context=f"schema_version={schema_version}",
    )
