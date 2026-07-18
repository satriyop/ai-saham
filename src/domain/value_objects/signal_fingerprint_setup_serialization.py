"""Setup-section serialization for SignalObservationFingerprint."""

from typing import TYPE_CHECKING, Any

from src.domain.value_objects.signal_label_parsing import (
    _optional_bool,
    _optional_float,
    _optional_int,
)

if TYPE_CHECKING:
    from src.domain.value_objects.signal_observation_fingerprint import (
        SignalObservationFingerprint,
    )


def _serialize_setup_fields(fp: "SignalObservationFingerprint") -> dict[str, Any]:
    return {
        "setup_family": fp.setup_family,
        "matched_setup_families": list(fp.matched_setup_families),
        "primary_setup_family": fp.primary_setup_family,
        "setup_family_source": fp.setup_family_source,
        "setup_family_rationale": list(fp.setup_family_rationale),
        "setup_name": fp.setup_name,
        "setup_phase": fp.setup_phase,
        "setup_phase_previous": fp.setup_phase_previous,
        "phase_sequence_valid": fp.phase_sequence_valid,
        "phase_age_sessions": fp.phase_age_sessions,
        # Legacy (schema 1/2) diagnostic fields — round-trips whatever this
        # fingerprint actually holds; never derived from the canonical fields.
        "phase_strength": fp.phase_strength,
        "phase_coverage_score": fp.phase_coverage_score,
        "phase_conviction_score": fp.phase_conviction_score,
        "phase_reasons": list(fp.phase_reasons),
        "phase_history": [dict(entry) for entry in fp.phase_history],
        # HIGH-2 canonical (schema 3) truthfully-named diagnostic phase metrics.
        "phase_detection_strength": fp.phase_detection_strength,
        "phase_input_coverage": fp.phase_input_coverage,
    }


def _parse_setup_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "setup_family": data.get("setup_family"),
        "matched_setup_families": tuple(
            str(v) for v in data.get("matched_setup_families") or ()
        ),
        "primary_setup_family": data.get("primary_setup_family"),
        "setup_family_source": data.get("setup_family_source"),
        "setup_family_rationale": tuple(
            str(v) for v in data.get("setup_family_rationale") or ()
        ),
        "setup_name": data.get("setup_name"),
        "setup_phase": data.get("setup_phase") or data.get("setup_phase_current"),
        "setup_phase_previous": data.get("setup_phase_previous"),
        "phase_sequence_valid": _optional_bool(data.get("phase_sequence_valid")),
        "phase_age_sessions": _optional_int(data.get("phase_age_sessions")),
        # Legacy (schema 1/2) fields — read only from the ambiguous legacy
        # keys those schemas actually produced. Never fall back to the
        # canonical phase_detection_strength/phase_input_coverage keys.
        "phase_strength": _optional_float(data.get("phase_strength")),
        "phase_coverage_score": _optional_float(data.get("phase_coverage_score")),
        "phase_conviction_score": _optional_float(data.get("phase_conviction_score")),
        "phase_reasons": tuple(str(v) for v in data.get("phase_reasons") or ()),
        "phase_history": tuple(
            dict(v) for v in data.get("phase_history") or () if isinstance(v, dict)
        ),
        # HIGH-2 canonical (schema 3) fields — read only from their own named
        # keys, never fabricated from the legacy phase_strength/phase_coverage_score.
        "phase_detection_strength": _optional_float(data.get("phase_detection_strength")),
        "phase_input_coverage": _optional_float(data.get("phase_input_coverage")),
    }
