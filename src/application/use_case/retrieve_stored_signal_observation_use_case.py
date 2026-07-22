"""Retrieve a persisted signal observation without recomputing it.

DQ-005 Slice A: this path is explicitly retrieval-only. It does not re-run the
engine, does not compare stored vs recomputed fields, and must not be described
as reproducibility/"replay" success. True recompute belongs to a later slice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
    CandidateObservationsRepository,
)


class ObservationRetrievalMode(str, Enum):
    """Hard-coded: this use case never recomputes."""

    RETRIEVAL_ONLY = "RETRIEVAL_ONLY"


class ObservationSelectionStatus(str, Enum):
    SELECTED = "SELECTED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class StoredObservationIdentity:
    """Exact stored row identity selected or offered for selection."""

    ticker: str
    snapshot_date: date
    captured_at: datetime
    workflow: str
    window_sessions: int
    config_hash: str
    data_as_of_date: date | None
    schema_version: int | None
    observation_contract: str | None = None
    semantic_compatibility_id: str | None = None

    @classmethod
    def from_observation(cls, observation: CandidateObservation) -> StoredObservationIdentity:
        payload = observation.payload or {}
        schema_version = payload.get("schema_version")
        try:
            parsed_schema = int(schema_version) if schema_version is not None else None
        except (TypeError, ValueError):
            parsed_schema = None
        sem = observation.semantic_compatibility_id
        return cls(
            ticker=observation.ticker.upper(),
            snapshot_date=observation.snapshot_date,
            captured_at=observation.captured_at,
            workflow=observation.workflow,
            window_sessions=observation.window_sessions,
            config_hash=observation.config_hash,
            data_as_of_date=observation.data_as_of_date,
            schema_version=parsed_schema,
            observation_contract=observation.observation_contract,
            semantic_compatibility_id=None if sem is None else str(sem),
        )


@dataclass(frozen=True)
class RetrieveStoredSignalObservationRequest:
    ticker: str
    snapshot_date: date
    observation_captured_at: datetime | None = None


@dataclass(frozen=True)
class RetrieveStoredSignalObservationResponse:
    mode: ObservationRetrievalMode = ObservationRetrievalMode.RETRIEVAL_ONLY
    status: ObservationSelectionStatus = ObservationSelectionStatus.NOT_FOUND
    observation: CandidateObservation | None = None
    selected_identity: StoredObservationIdentity | None = None
    candidates: tuple[StoredObservationIdentity, ...] = field(default_factory=tuple)


class RetrieveStoredSignalObservationUseCase:
    """Load one stored observation by explicit identity rules.

    Selection policy (DQ-005 Slice A):
    - If ``observation_captured_at`` is provided → ``get_at`` that version.
    - If omitted and exactly one row exists for ticker/date → select it and
      name its identity (no silent multi-version pick).
    - If omitted and multiple rows exist → ``AMBIGUOUS`` with candidate
      identities; never call ``get_latest``.
    """

    def __init__(self, repository: CandidateObservationsRepository) -> None:
        self._repository = repository

    def execute(
        self, request: RetrieveStoredSignalObservationRequest
    ) -> RetrieveStoredSignalObservationResponse:
        ticker = request.ticker.upper()
        day = request.snapshot_date

        if request.observation_captured_at is not None:
            observation = self._repository.get_at(
                ticker, day, request.observation_captured_at
            )
            if observation is None:
                return RetrieveStoredSignalObservationResponse(
                    status=ObservationSelectionStatus.NOT_FOUND,
                )
            identity = StoredObservationIdentity.from_observation(observation)
            return RetrieveStoredSignalObservationResponse(
                status=ObservationSelectionStatus.SELECTED,
                observation=observation,
                selected_identity=identity,
            )

        versions = self._versions_for(ticker, day)
        if not versions:
            return RetrieveStoredSignalObservationResponse(
                status=ObservationSelectionStatus.NOT_FOUND,
            )
        if len(versions) > 1:
            candidates = tuple(
                StoredObservationIdentity.from_observation(obs) for obs in versions
            )
            return RetrieveStoredSignalObservationResponse(
                status=ObservationSelectionStatus.AMBIGUOUS,
                candidates=candidates,
            )

        observation = versions[0]
        identity = StoredObservationIdentity.from_observation(observation)
        return RetrieveStoredSignalObservationResponse(
            status=ObservationSelectionStatus.SELECTED,
            observation=observation,
            selected_identity=identity,
        )

    def _versions_for(
        self, ticker: str, snapshot_date: date
    ) -> list[CandidateObservation]:
        rows = self._repository.list_all_by_date(snapshot_date)
        matched = [obs for obs in rows if obs.ticker.upper() == ticker]
        # Stable order: newest first so AMBIGUOUS listings are predictable.
        return sorted(matched, key=lambda obs: obs.captured_at, reverse=True)
