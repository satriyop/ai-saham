from __future__ import annotations

from datetime import date, datetime

from src.application.use_case.replay_signal_observation_use_case import (
    ReplaySignalObservationRequest,
    ReplaySignalObservationUseCase,
)
from src.domain.ports.candidate_observations_repository import CandidateObservation


class FakeObservationRepo:
    def __init__(self, observation=None):
        self.observation = observation
        self.calls = []

    def get_latest(self, ticker, snapshot_date):
        self.calls.append((ticker, snapshot_date))
        return self.observation


def test_replay_reads_repository_without_fetching():
    obs = CandidateObservation(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 3),
        captured_at=datetime(2026, 7, 3, 9, 0, 0),
        payload={"schema_version": 1},
    )
    repo = FakeObservationRepo(obs)

    response = ReplaySignalObservationUseCase(repo).execute(
        ReplaySignalObservationRequest(ticker="bbca", snapshot_date=date(2026, 7, 3))
    )

    assert response.observation == obs
    assert repo.calls == [("BBCA", date(2026, 7, 3))]


def test_replay_returns_none_when_missing():
    repo = FakeObservationRepo(None)

    response = ReplaySignalObservationUseCase(repo).execute(
        ReplaySignalObservationRequest(ticker="BBCA", snapshot_date=date(2026, 7, 3))
    )

    assert response.observation is None
