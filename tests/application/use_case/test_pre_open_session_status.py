"""Tests for GetPreOpenSessionStatusUseCase session readiness."""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src.application.use_case.database_learning_lifecycle_use_case import (
    GetPreOpenSessionStatusUseCase,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
    LearningTrackSnapshot,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

WIB = ZoneInfo("Asia/Jakarta")
SESSION = date(2026, 6, 18)


def _add_obs(repo, ticker="BBCA", *, compatibility_id="compat-a"):
    obs = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id=compatibility_id,
        cutoff_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
        universe_id="iev:2026-06-18",
        window_id=f"{ticker}:2026-06-18",
        decision_payload={"ticker": ticker, "screen_result": "pass"},
        captured_at=datetime(2026, 6, 18, 8, 57, tzinfo=WIB),
    )
    assert repo.add_observation(obs)
    return obs


def test_status_empty_session(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "s.db")
    status = GetPreOpenSessionStatusUseCase(
        observations=repo,
        tracks=repo,
        labels=repo,
        evaluations=repo,
    ).execute(SESSION)
    assert status.observation_count == 0
    assert "No capture" in status.next_actions[0]


def test_status_ready_to_analyze_with_opening_price(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "s.db")
    obs = _add_obs(repo)
    snap = LearningTrackSnapshot.create(
        observation_id=obs.observation_id,
        sampled_at=datetime(2026, 6, 18, 9, 0, 5, tzinfo=WIB),
        source="stockbit.opening_track",
        snapshot_payload={
            "opening_price": "10050",
            "opening_price_source": "order_book_lastprice",
        },
        captured_at=datetime(2026, 6, 18, 9, 0, 5, tzinfo=WIB),
    )
    assert repo.add_track_snapshot(snap)

    status = GetPreOpenSessionStatusUseCase(
        observations=repo,
        tracks=repo,
        labels=repo,
        evaluations=repo,
    ).execute(SESSION)
    assert status.observation_count == 1
    assert status.with_opening_price == 1
    assert status.missing_opening_price == 0
    line = status.lines[0]
    assert line.readiness == "READY_TO_ANALYZE"
    assert line.has_opening_price is True
    assert line.opening_snapshot_id == snap.snapshot_id
    assert any("analyze pre-open" in a for a in status.next_actions)


def test_status_missing_open(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "s.db")
    obs = _add_obs(repo)
    assert repo.add_track_snapshot(
        LearningTrackSnapshot.create(
            observation_id=obs.observation_id,
            sampled_at=datetime(2026, 6, 18, 9, 1, tzinfo=WIB),
            source="stockbit.opening_track",
            snapshot_payload={"mid_price": 100.0, "opening_price_status": "MISSING"},
            captured_at=datetime(2026, 6, 18, 9, 1, tzinfo=WIB),
        )
    )
    status = GetPreOpenSessionStatusUseCase(
        observations=repo,
        tracks=repo,
        labels=repo,
        evaluations=repo,
    ).execute(SESSION)
    assert status.missing_opening_price == 1
    assert status.lines[0].readiness == "MISSING_OPEN"
    assert any("MISSING_OPEN" in a for a in status.next_actions)
