from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from src.application.use_case.opening_track_use_case import (
    OpeningTrackRequest,
    OpeningTrackUseCase,
)
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

WIB = ZoneInfo("Asia/Jakarta")


class Browser:
    def fetch_order_book_top_of_book(self, ticker):
        return SimpleNamespace(
            bid=SimpleNamespace(price=100),
            offer=SimpleNamespace(price=102),
        )


def test_force_track_persists_observation_linked_snapshot(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    at = datetime(2026, 7, 27, 8, 57, tzinfo=WIB)
    observation = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="compat-1",
        cutoff_at=at,
        universe_id="iev:2026-07-27",
        window_id="BBCA:2026-07-27",
        decision_payload={"ticker": "BBCA"},
        captured_at=at,
    )
    repository.add_observation(observation)

    snapshots = OpeningTrackUseCase(
        Browser(),
        repository=repository,
    ).execute(
        OpeningTrackRequest(
            observation_ids_by_ticker={"BBCA": observation.observation_id},
            force=True,
        )
    )

    persisted = repository.list_track_snapshots(observation.observation_id)
    assert len(snapshots) == 1
    assert len(persisted) == 1
    assert persisted[0].snapshot_payload["mid_price"] == 101.0
