"""Setup phase fingerprint serialization for accumulation observation payloads.

HIGH-2 schema 3: persists truthfully-named diagnostic phase metrics only —
phase_input_coverage and phase_detection_strength. There is no
phase_conviction_score/phase_coverage_score/phase_strength in schema 3;
those ambiguous v1/v2 field names must not be reintroduced here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.value_objects.setup_phase import SetupPhaseSnapshot


def _setup_phase_fingerprint(
    setup_phase: "SetupPhaseSnapshot | None",
) -> dict:
    if setup_phase is None:
        return {
            "setup_phase_current": None,
            "setup_phase_previous": None,
            "phase_sequence_valid": None,
            "phase_age_sessions": None,
            "phase_detection_strength": None,
            "phase_reasons": [],
            "phase_history": [],
            "phase_input_coverage": None,
            "volume_dry_up_ratio_at_signal": None,
            "volume_expansion_ratio_at_signal": None,
            "volume_dry_up_confirmed": None,
            "volume_expansion_confirmed": None,
            "volume_trigger_confirmed": None,
        }
    return {
        "setup_phase_current": setup_phase.current_phase.value,
        "setup_phase_previous": (
            setup_phase.previous_phase.value if setup_phase.previous_phase else None
        ),
        "phase_sequence_valid": setup_phase.sequence_valid,
        "phase_age_sessions": setup_phase.phase_age_sessions,
        "phase_detection_strength": setup_phase.phase_detection_strength,
        "phase_reasons": list(setup_phase.reasons),
        "phase_history": [entry.to_dict() for entry in setup_phase.history],
        "phase_input_coverage": setup_phase.phase_input_coverage,
        "volume_dry_up_ratio_at_signal": setup_phase.volume_dry_up_ratio,
        "volume_expansion_ratio_at_signal": setup_phase.volume_expansion_ratio,
        "volume_dry_up_confirmed": setup_phase.volume_dry_up_confirmed,
        "volume_expansion_confirmed": setup_phase.volume_expansion_confirmed,
        "volume_trigger_confirmed": setup_phase.volume_trigger_confirmed,
    }
