"""Read persisted setup phase history for deterministic sequence validation.

Layer: Application
Depends on: repository port + domain value objects only.
"""

from __future__ import annotations

from datetime import date

from src.domain.ports.candidate_observations_repository import (
    CandidateObservationsRepository,
)
from src.domain.value_objects.setup_phase import SetupPhaseState


def load_previous_setup_phases(
    repository: CandidateObservationsRepository | None,
    *,
    ticker: str,
    before_date: date,
    setup_family: str | None = None,
    limit: int = 20,
) -> tuple[SetupPhaseState, ...]:
    """Return prior persisted phases oldest-to-newest for sequence validation."""
    if repository is None:
        return ()
    observations = repository.list_recent(
        ticker,
        before_date=before_date,
        limit=limit,
    )
    phases: list[SetupPhaseState] = []
    expected_family = _normalize_setup_family(setup_family)
    for observation in reversed(observations):
        fingerprint = (observation.payload or {}).get("sub_signal_fingerprint") or {}
        if expected_family is not None:
            observed_family = _normalize_setup_family(fingerprint.get("setup_family"))
            if observed_family is None:
                if not _allows_generic_screen_history(observation.payload, expected_family):
                    continue
            elif observed_family != expected_family:
                continue
        phase = _parse_phase(fingerprint.get("setup_phase_current"))
        if phase is not None:
            phases.append(phase)
    return tuple(phases)


def _parse_phase(value: object) -> SetupPhaseState | None:
    if value is None:
        return None
    try:
        return SetupPhaseState(str(value))
    except ValueError:
        return None


def _normalize_setup_family(value: object) -> str | None:
    if not value:
        return None
    return str(value).strip().lower().replace("_", "-")


def _allows_generic_screen_history(payload: dict, expected_family: str) -> bool:
    return (
        payload.get("workflow") == "screen_accum"
        and expected_family in {"accumulation", "foreign-bounce"}
    )
