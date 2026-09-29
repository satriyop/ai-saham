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
from src.domain.value_objects.screener_result import MoverData
from src.infrastructure.persistence.iev_json_sidecar import IEVJsonSidecarWriter
from src.infrastructure.persistence.iev_session_capture_lookup import (
    IevSessionCaptureLookup,
)
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

WIB = ZoneInfo("Asia/Jakarta")
SESSION = date(2026, 6, 18)


def _status_uc(repo, *, iev_capture=None):
    return GetPreOpenSessionStatusUseCase(
        observations=repo,
        tracks=repo,
        labels=repo,
        evaluations=repo,
        iev_capture=iev_capture,
    )


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
        producer_source_revision="ai-saham@test",
    )
    assert repo.add_observation(obs)
    return obs


def test_status_empty_session(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "s.db")
    status = _status_uc(repo).execute(SESSION)
    assert status.observation_count == 0
    assert status.miss_reason is None
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

    status = _status_uc(repo).execute(SESSION)
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
    status = _status_uc(repo).execute(SESSION)
    assert status.missing_opening_price == 1
    assert status.lines[0].readiness == "MISSING_OPEN"
    assert any("MISSING_OPEN" in a for a in status.next_actions)


def _lookup(tmp_path: Path) -> IevSessionCaptureLookup:
    return IevSessionCaptureLookup(
        db_path=tmp_path / "s.db",
        sidecar_root=tmp_path / "data" / "iev",
    )


def test_status_late_sidecar_empty_obs_is_late_capture(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "s.db")
    IEVJsonSidecarWriter(tmp_path / "data" / "iev").write_snapshot(
        SESSION,
        [MoverData("BBCA", 100_000, 5900)],
        captured_at=datetime(2026, 6, 18, 9, 24, 24, tzinfo=WIB),
        top_n=50,
    )
    status = _status_uc(repo, iev_capture=_lookup(tmp_path)).execute(SESSION)
    assert status.observation_count == 0
    assert status.miss_reason == "late_capture"
    assert any("late_capture" in action for action in status.next_actions)
    assert not any(
        "run `saham research pre-open capture`" in action for action in status.next_actions
    )
    assert not any("NCP window" in action for action in status.next_actions)


def test_status_on_time_empty_day_does_not_invent_late_capture(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "s.db")
    IEVJsonSidecarWriter(tmp_path / "data" / "iev").write_snapshot(
        SESSION,
        [MoverData("BBCA", 100_000, 5900)],
        captured_at=datetime(2026, 6, 18, 8, 57, 3, tzinfo=WIB),
        top_n=50,
    )
    status = _status_uc(repo, iev_capture=_lookup(tmp_path)).execute(SESSION)
    assert status.observation_count == 0
    assert status.miss_reason is None
    assert "No capture" in status.next_actions[0]


def test_status_empty_day_without_iev_does_not_invent_late_capture(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "s.db")
    status = _status_uc(repo, iev_capture=_lookup(tmp_path)).execute(SESSION)
    assert status.observation_count == 0
    assert status.miss_reason is None


def test_status_late_sqlite_fallback_empty_obs_is_late_capture(tmp_path: Path) -> None:
    db_path = tmp_path / "s.db"
    repo = SQLiteLearningArtifactRepository(db_path)
    SQLiteIEVRepository(db_path).save_snapshot(
        SESSION,
        [MoverData("BBCA", 100_000, 5900)],
        collected_at=datetime(2026, 6, 18, 9, 24, 24),
        collection_started_at=datetime(2026, 6, 18, 9, 24, 0),
    )
    status = _status_uc(repo, iev_capture=_lookup(tmp_path)).execute(SESSION)
    assert status.observation_count == 0
    assert status.miss_reason == "late_capture"


def test_status_late_iev_does_not_override_existing_observations(tmp_path: Path) -> None:
    repo = SQLiteLearningArtifactRepository(tmp_path / "s.db")
    _add_obs(repo)
    IEVJsonSidecarWriter(tmp_path / "data" / "iev").write_snapshot(
        SESSION,
        [MoverData("BBCA", 100_000, 5900)],
        captured_at=datetime(2026, 6, 18, 9, 24, 24, tzinfo=WIB),
        top_n=50,
    )
    status = _status_uc(repo, iev_capture=_lookup(tmp_path)).execute(SESSION)
    assert status.observation_count == 1
    assert status.miss_reason is None
