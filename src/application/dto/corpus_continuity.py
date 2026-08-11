"""
DTOs for learning-corpus session continuity.

Answers one question: for a given assessment purpose and cohort, which trading
sessions inside the corpus window are missing, thin, or unattestable?

Continuity is a *policy* question, not a formatting one — what counts as a hole
depends on calendar authority and on an expected per-session observation count.
It therefore lives in the application layer, and adapters only render the result.

Layer: Application (DTO)
Depends on: Domain value objects only
AI usage: None
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from src.domain.value_objects.learning_artifacts import AssessmentPurpose


class SessionContinuityStatus(str, Enum):
    """Per-session verdict.

    ``NO_CALENDAR_AUTHORITY`` is deliberately distinct from ``OK``. Trading
    session calendar snapshots are attested per coverage window, so a date
    outside every stored window is *unknown*, not *fine*. Collapsing the two
    would silently mark unverifiable dates healthy.
    """

    OK = "OK"
    MISSING = "MISSING"
    UNDER_COVERED = "UNDER_COVERED"
    NO_CALENDAR_AUTHORITY = "NO_CALENDAR_AUTHORITY"


@dataclass(frozen=True)
class SessionContinuityRow:
    """One trading session inside the audited window."""

    session_date: date
    status: SessionContinuityStatus
    observation_count: int
    expected_observation_count: int | None


@dataclass(frozen=True)
class CorpusContinuityRequest:
    """Audit window for one purpose/cohort.

    ``window_start`` defaults to the cohort's earliest observed session, so the
    audit never reports the whole of market history as missing.

    ``expected_observation_count`` is the per-session cross-sectional width the
    caller *declares* (e.g. 45 for an LQ45 accum capture). Only a declared width
    is used to judge thinness. A width guessed from the corpus cannot detect a
    systematically thin corpus, and for purposes whose width is genuinely
    variable — pre-open captures only as many candidates as pass the filters —
    there is no correct width to guess. When it is ``None`` the audit still
    reports the modal observed width for information but never flags
    ``UNDER_COVERED``.

    ``min_coverage_fraction`` is the share of the declared width a session must
    reach to count as complete. The default tolerates an ordinary suspension
    (44/45) while still catching a materially truncated capture.
    """

    purpose: AssessmentPurpose
    as_of: date
    compatibility_id: str | None = None
    window_start: date | None = None
    expected_observation_count: int | None = None
    alert_lookback_sessions: int | None = None
    min_coverage_fraction: float = 0.9


@dataclass(frozen=True)
class CorpusContinuityResponse:
    """Continuity verdict for one purpose/cohort window."""

    purpose: AssessmentPurpose
    compatibility_id: str | None
    window_start: date | None
    window_end: date
    rows: tuple[SessionContinuityRow, ...]
    calendar_snapshot_ids: tuple[str, ...]
    expected_observation_count: int | None
    observed_modal_width: int | None
    operationally_healthy: bool
    alert_lookback_sessions: int | None

    @property
    def missing_sessions(self) -> tuple[date, ...]:
        return tuple(
            row.session_date for row in self.rows if row.status is SessionContinuityStatus.MISSING
        )

    @property
    def under_covered_sessions(self) -> tuple[date, ...]:
        return tuple(
            row.session_date
            for row in self.rows
            if row.status is SessionContinuityStatus.UNDER_COVERED
        )

    @property
    def unattestable_sessions(self) -> tuple[date, ...]:
        return tuple(
            row.session_date
            for row in self.rows
            if row.status is SessionContinuityStatus.NO_CALENDAR_AUTHORITY
        )

    def counts(self) -> dict[str, int]:
        tally = {status.value: 0 for status in SessionContinuityStatus}
        for row in self.rows:
            tally[row.status.value] += 1
        return tally
