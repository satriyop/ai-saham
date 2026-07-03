"""Replay a persisted signal/candidate observation without live providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.ports.candidate_observations_repository import (
    CandidateObservation,
    CandidateObservationsRepository,
)


@dataclass(frozen=True)
class ReplaySignalObservationRequest:
    ticker: str
    snapshot_date: date


@dataclass(frozen=True)
class ReplaySignalObservationResponse:
    observation: CandidateObservation | None


class ReplaySignalObservationUseCase:
    def __init__(self, repository: CandidateObservationsRepository) -> None:
        self._repository = repository

    def execute(
        self, request: ReplaySignalObservationRequest
    ) -> ReplaySignalObservationResponse:
        observation = self._repository.get_latest(
            request.ticker.upper(),
            request.snapshot_date,
        )
        return ReplaySignalObservationResponse(observation=observation)
