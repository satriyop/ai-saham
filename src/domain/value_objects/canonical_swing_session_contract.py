"""Canonical swing effective-session contract for one candidate observation.

A swing-trading decision is made after IDX session close, so the captured
observation's snapshot_date, latest_completed_session, and analysis_as_of
must all be the same date. Any divergence means a stale, pre-close, or
otherwise non-canonical capture and must not contribute a canonical
forward label.

This narrows (does not relax) the looser ``latest_completed_session <=
analysis_as_of`` rule encoded in :class:`ArtifactProvenance` for the
swing-only canonical observation path.

Layer: Domain (pure value object, no I/O)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CanonicalSwingSessionContract:
    """Effective-session contract for a canonical swing observation.

    All three dates must be equal because a swing observation is anchored
    on the closed IDX session: the snapshot is the session, that session
    is the latest completed one at decision time, and the analysis is
    performed as of that same session.
    """

    snapshot_date: date
    latest_completed_session: date
    analysis_as_of: date

    def __post_init__(self) -> None:
        if self.snapshot_date != self.latest_completed_session:
            raise ValueError(
                f"snapshot_date ({self.snapshot_date}) must equal "
                f"latest_completed_session ({self.latest_completed_session}) "
                f"for a canonical swing observation"
            )
        if self.snapshot_date != self.analysis_as_of:
            raise ValueError(
                f"snapshot_date ({self.snapshot_date}) must equal "
                f"analysis_as_of ({self.analysis_as_of}) for a canonical "
                "swing observation"
            )

    @classmethod
    def from_observation_fields(
        cls,
        snapshot_date: date,
        latest_completed_session: date | None,
        analysis_as_of: date | None,
    ) -> "CanonicalSwingSessionContract":
        """Build the contract from the three observation fields.

        Raises ``ValueError`` if either provenance field is missing or if
        the three dates do not all agree — both conditions make the
        observation ineligible to produce a canonical forward label.
        """
        if latest_completed_session is None or analysis_as_of is None:
            raise ValueError(
                "canonical swing observation requires non-None "
                "latest_completed_session and analysis_as_of"
            )
        return cls(
            snapshot_date=snapshot_date,
            latest_completed_session=latest_completed_session,
            analysis_as_of=analysis_as_of,
        )
