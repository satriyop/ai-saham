from __future__ import annotations

from datetime import date, datetime

from src.application.use_case.retrieve_stored_signal_observation_use_case import (
    ObservationRetrievalMode,
    ObservationSelectionStatus,
    RetrieveStoredSignalObservationRequest,
    RetrieveStoredSignalObservationUseCase,
)
from src.domain.ports.candidate_observations_repository import CandidateObservation


class FakeObservationRepo:
    def __init__(self, observations=None):
        self.observations = list(observations or [])
        self.get_at_calls = []
        self.get_latest_calls = []
        self.list_all_by_date_calls = []

    def get_latest(self, ticker, snapshot_date):
        self.get_latest_calls.append((ticker, snapshot_date))
        raise AssertionError(
            "DQ-005 Slice A must not use get_latest (silent version pick)"
        )

    def get_at(self, ticker, snapshot_date, captured_at):
        self.get_at_calls.append((ticker, snapshot_date, captured_at))
        for obs in self.observations:
            if (
                obs.ticker.upper() == ticker.upper()
                and obs.snapshot_date == snapshot_date
                and obs.captured_at == captured_at
            ):
                return obs
        return None

    def list_all_by_date(self, snapshot_date):
        self.list_all_by_date_calls.append(snapshot_date)
        return [obs for obs in self.observations if obs.snapshot_date == snapshot_date]


def _obs(
    *,
    captured_at: datetime,
    ticker: str = "BBCA",
    day: date = date(2026, 7, 3),
    config_hash: str = "hash-a",
    window_sessions: int = 7,
    schema_version: int = 5,
) -> CandidateObservation:
    return CandidateObservation(
        ticker=ticker,
        snapshot_date=day,
        captured_at=captured_at,
        payload={"schema_version": schema_version, "ticker": ticker},
        window_sessions=window_sessions,
        config_hash=config_hash,
        data_as_of_date=day,
    )


def test_retrieval_mode_is_always_retrieval_only():
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0))
    response = RetrieveStoredSignalObservationUseCase(FakeObservationRepo([obs])).execute(
        RetrieveStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )
    assert response.mode is ObservationRetrievalMode.RETRIEVAL_ONLY
    assert response.status is ObservationSelectionStatus.SELECTED
    assert response.selected_identity is not None
    assert response.selected_identity.captured_at == datetime(2026, 7, 3, 9, 0, 0)


def test_single_version_without_captured_at_selects_and_names_identity():
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0), config_hash="cfg-1")
    repo = FakeObservationRepo([obs])

    response = RetrieveStoredSignalObservationUseCase(repo).execute(
        RetrieveStoredSignalObservationRequest(
            ticker="bbca", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationSelectionStatus.SELECTED
    assert response.observation == obs
    assert response.selected_identity is not None
    assert response.selected_identity.ticker == "BBCA"
    assert response.selected_identity.config_hash == "cfg-1"
    assert response.selected_identity.window_sessions == 7
    assert response.selected_identity.schema_version == 5
    assert repo.get_latest_calls == []
    assert repo.list_all_by_date_calls == [date(2026, 7, 3)]


def test_multiple_versions_without_captured_at_are_ambiguous():
    older = _obs(
        captured_at=datetime(2026, 7, 3, 9, 0, 0),
        config_hash="cfg-old",
        window_sessions=7,
    )
    newer = _obs(
        captured_at=datetime(2026, 7, 3, 10, 0, 0),
        config_hash="cfg-new",
        window_sessions=20,
    )
    repo = FakeObservationRepo([older, newer])

    response = RetrieveStoredSignalObservationUseCase(repo).execute(
        RetrieveStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationSelectionStatus.AMBIGUOUS
    assert response.observation is None
    assert response.selected_identity is None
    assert [c.captured_at for c in response.candidates] == [
        datetime(2026, 7, 3, 10, 0, 0),
        datetime(2026, 7, 3, 9, 0, 0),
    ]
    assert repo.get_latest_calls == []
    assert repo.get_at_calls == []


def test_explicit_captured_at_selects_that_version_not_latest():
    older = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0), config_hash="cfg-old")
    newer = _obs(captured_at=datetime(2026, 7, 3, 10, 0, 0), config_hash="cfg-new")
    repo = FakeObservationRepo([older, newer])

    response = RetrieveStoredSignalObservationUseCase(repo).execute(
        RetrieveStoredSignalObservationRequest(
            ticker="BBCA",
            snapshot_date=date(2026, 7, 3),
            observation_captured_at=datetime(2026, 7, 3, 9, 0, 0),
        )
    )

    assert response.status is ObservationSelectionStatus.SELECTED
    assert response.observation == older
    assert response.selected_identity is not None
    assert response.selected_identity.captured_at == datetime(2026, 7, 3, 9, 0, 0)
    assert response.selected_identity.config_hash == "cfg-old"
    assert repo.get_at_calls == [
        ("BBCA", date(2026, 7, 3), datetime(2026, 7, 3, 9, 0, 0))
    ]
    assert repo.get_latest_calls == []


def test_explicit_captured_at_missing_is_not_found():
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0))
    repo = FakeObservationRepo([obs])

    response = RetrieveStoredSignalObservationUseCase(repo).execute(
        RetrieveStoredSignalObservationRequest(
            ticker="BBCA",
            snapshot_date=date(2026, 7, 3),
            observation_captured_at=datetime(2026, 7, 3, 11, 0, 0),
        )
    )

    assert response.status is ObservationSelectionStatus.NOT_FOUND
    assert response.observation is None


def test_no_rows_is_not_found():
    repo = FakeObservationRepo([])

    response = RetrieveStoredSignalObservationUseCase(repo).execute(
        RetrieveStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )

    assert response.status is ObservationSelectionStatus.NOT_FOUND
    assert response.mode is ObservationRetrievalMode.RETRIEVAL_ONLY


def test_never_calls_get_latest_even_for_single_row():
    """Negative contract: silent latest-pick path is removed."""
    obs = _obs(captured_at=datetime(2026, 7, 3, 9, 0, 0))
    repo = FakeObservationRepo([obs])
    RetrieveStoredSignalObservationUseCase(repo).execute(
        RetrieveStoredSignalObservationRequest(
            ticker="BBCA", snapshot_date=date(2026, 7, 3)
        )
    )
    assert repo.get_latest_calls == []
