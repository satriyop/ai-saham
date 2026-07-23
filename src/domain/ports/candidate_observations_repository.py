"""Repository port for replayable candidate evidence observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from src.domain.ports.observation_risk_assessment_repository import (
    ObservationRiskAssessmentRecord,
)

from src.domain.value_objects.signal_artifact_identity import (
    SemanticCompatibilityId,
    SignalArtifactIdentity,
)


@dataclass(frozen=True)
class CandidateObservation:
    ticker: str
    snapshot_date: date
    captured_at: datetime
    payload: dict
    # Canonical identity, together with ticker/snapshot_date: two observations
    # sharing all of (ticker, snapshot_date, workflow, window_sessions,
    # data_as_of_date, config_hash) are the SAME canonical observation and a
    # second save_many() call must replace, not duplicate, the first.
    # captured_at is metadata only — never part of identity.
    workflow: str = "screen_accum"
    window_sessions: int = 0
    data_as_of_date: date | None = None
    config_hash: str = ""
    # Effective-session provenance (DQ-002E). Metadata only — copied verbatim
    # from an already-resolved EffectiveMarketSession by the recording use
    # case/persister, never recomputed here or by any repository. Not part of
    # canonical identity: two observations differing only in these fields are
    # still the same canonical observation.
    decision_at: datetime | None = None
    latest_completed_session: date | None = None
    analysis_as_of: date | None = None
    market_session_name: str | None = None
    is_eod_pending: bool | None = None
    resolution_source: str | None = None
    resolution_notes: tuple[str, ...] = ()
    artifact_identity: SignalArtifactIdentity | None = None
    # Lean observation identity (DQ-003 Slice A). Metadata only — never part of
    # canonical identity: two observations differing only in these fields are
    # still the same canonical observation. observation_contract is the
    # canonical contract label ("accumulation-discovery"); semantic_compatibility_id
    # is the whole-config-hash cohort tag. These are the lean subset of the
    # parked SignalArtifactIdentity; they are persisted directly (the
    # semantic_compatibility_id column is written from this field, not via the
    # all-three-or-none artifact-identity codec).
    observation_contract: str | None = None
    semantic_compatibility_id: SemanticCompatibilityId | None = None


class CandidateObservationsRepository(Protocol):
    """Local repository for schema-versioned candidate observation payloads."""

    def save_many(
        self,
        observations: list[CandidateObservation],
        *,
        risk_records: list[ObservationRiskAssessmentRecord] | None = None,
    ) -> None:
        """Upsert observations by canonical identity for later replay.

        Identity is (ticker, snapshot_date, workflow, window_sessions,
        data_as_of_date, config_hash). Saving an observation that matches an
        existing identity replaces its payload/captured_at in place rather
        than appending a duplicate row.

        When risk_records is provided, implementations that support child
        persistence write observation_risk_assessments in the same transaction
        as the parent upserts.
        """
        ...

    def get_latest(self, ticker: str, snapshot_date: date) -> CandidateObservation | None:
        """Return latest saved observation for ticker/date, if any."""
        ...

    def get_at(
        self,
        ticker: str,
        snapshot_date: date,
        captured_at: datetime,
    ) -> CandidateObservation | None:
        """Return the observation for ticker/date/captured_at, if any."""
        ...

    def list_recent(
        self,
        ticker: str,
        *,
        before_date: date | None = None,
        limit: int = 20,
    ) -> list[CandidateObservation]:
        """Return recent observations for ticker, newest first.

        before_date excludes same-day observations so callers can reconstruct
        prior state without reading the row currently being written.
        """
        ...

    def list_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return latest observation per ticker for the given snapshot date.

        Collapses to one row per ticker — a UI/readiness display convenience.
        Do not use this for label generation: it silently drops all but the
        most-recently-captured canonical observation when a ticker has
        several (e.g. one per window_sessions). Use list_canonical_by_date()
        for anything that must cover every canonical row.
        """
        ...

    def list_all_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return all observations for the given snapshot date."""
        ...

    def list_canonical_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return every canonical observation for the date.

        Canonical = config_hash != '' AND schema_version ==
        CANDIDATE_OBSERVATION_SCHEMA_VERSION. Unlike list_by_date(), this does
        not collapse multiple canonical rows for the same ticker (e.g. one per
        window_sessions) down to the latest one — every canonical identity is
        returned. Legacy rows (no config_hash, or an older/newer schema) are
        excluded. This is what label generation must use so every recorded
        window gets labeled, not just the most recently captured one.
        """
        ...

    def list_snapshot_dates(self) -> list[date]:
        """Return snapshot dates with saved observations, oldest first."""
        ...

    def list_canonical_snapshot_dates(self) -> list[date]:
        """Return snapshot dates containing at least one canonical observation.

        Canonical = config_hash != '' and schema_version = current schema.
        Dates whose only rows are legacy/non-canonical are excluded.
        """
        ...

    def list_latest_canonical_by_date(self, snapshot_date: date) -> list[CandidateObservation]:
        """Return the latest canonical observation per ticker for the date.

        Canonical filtering (config_hash != '' and schema_version = current
        schema) is applied before selecting the latest row per ticker, so a
        newer legacy row can never displace an older canonical row.
        """
        ...
