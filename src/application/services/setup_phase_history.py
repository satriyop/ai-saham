"""Read persisted setup phase history for deterministic sequence validation.

Layer: Application
Depends on: repository port + domain value objects only.
"""

from __future__ import annotations

from datetime import date

from src.domain.ports.learning_artifact_repositories import (
    LearningObservationRepository,
)
from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.domain.value_objects.setup_phase import SetupPhaseState


def load_previous_setup_phases(
    repository: LearningObservationRepository | None,
    *,
    ticker: str,
    before_date: date,
    setup_family: str | None = None,
    limit: int = 20,
) -> tuple[SetupPhaseState, ...]:
    """Return prior persisted phases oldest-to-newest for sequence validation."""
    if repository is None:
        return ()
    observations = [
        observation
        for observation in repository.list_observations(
            AssessmentPurpose.ACCUMULATION_DISCOVERY
        )
        if observation.cutoff_at.date() < before_date
        and _payload_ticker(observation.decision_payload) == ticker.upper()
    ][-limit:]
    phases: list[SetupPhaseState] = []
    expected_family = _normalize_setup_family(setup_family)
    for observation in reversed(observations):
        payload = dict(observation.decision_payload)
        fingerprint = payload.get("sub_signal_fingerprint") or {}
        phase = _parse_phase(fingerprint.get("setup_phase_current"))
        if expected_family is not None:
            observed_family = _normalize_setup_family(fingerprint.get("setup_family"))
            if observed_family is None:
                if not _allows_generic_screen_history(
                    payload, expected_family, phase
                ):
                    continue
            elif observed_family != expected_family:
                continue
        if phase is not None:
            phases.append(phase)
    return tuple(phases)


def _payload_ticker(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    ticker = payload.get("ticker")
    return ticker.upper() if isinstance(ticker, str) else None


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


def _allows_generic_screen_history(
    payload: dict,
    expected_family: str,
    phase: SetupPhaseState | None,
) -> bool:
    if payload.get("workflow") != "screen_accum":
        return False
    if expected_family in {"accumulation", "foreign-bounce"}:
        return True
    if expected_family in {"breakout", "coiled-spring"}:
        # `screen accum` is the only workflow that persists lifecycle-phase
        # observations today (`analyze swing` never writes candidate
        # observations, only reads them) — without this, breakout/coiled-spring
        # required_sequence=[COMPRESSION, BREAKOUT_CONFIRMATION] could never
        # accumulate the prior COMPRESSION history it needs from normal use.
        # Only COMPRESSION is accepted generically: it's a benign, family-
        # agnostic lifecycle fact, whereas a generic screen scan reaching
        # BREAKOUT_CONFIRMATION should not itself count as a validated entry
        # signal for a specific named setup's gates.
        return phase == SetupPhaseState.COMPRESSION
    return False
