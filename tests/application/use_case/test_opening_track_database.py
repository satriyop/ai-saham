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


class OrderBookWithLast:
    def fetch_snapshot(self, ticker):
        return SimpleNamespace(
            last_price=105.0,
            to_dict=lambda: {"last_price": 105.0, "best_bid": 100, "best_offer": 102},
        )


class OrderBookMidOnly:
    def fetch_snapshot(self, ticker):
        return SimpleNamespace(
            last_price=None,
            to_dict=lambda: {"best_bid": 100, "best_offer": 102},
        )


def _obs(repository, ticker="BBCA"):
    at = datetime(2026, 7, 27, 8, 57, tzinfo=WIB)
    observation = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="compat-1",
        cutoff_at=at,
        universe_id="iev:2026-07-27",
        window_id=f"{ticker}:2026-07-27",
        decision_payload={"ticker": ticker},
        captured_at=at,
    )
    repository.add_observation(observation)
    return observation


def test_force_track_persists_observation_linked_snapshot(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _obs(repository)

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
    assert "opening_price" not in persisted[0].snapshot_payload
    assert persisted[0].snapshot_payload.get("opening_price_status") == "MISSING"


def test_track_promotes_order_book_last_price_to_opening_price(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _obs(repository)

    OpeningTrackUseCase(
        Browser(),
        repository=repository,
        order_book_provider=OrderBookWithLast(),
    ).execute(
        OpeningTrackRequest(
            observation_ids_by_ticker={"BBCA": observation.observation_id},
            force=True,
        )
    )
    payload = repository.list_track_snapshots(observation.observation_id)[0].snapshot_payload
    assert payload["opening_price"] == 105.0
    assert payload["opening_price_source"] == "order_book_lastprice"
    assert payload["opening_price_confidence"] == "MEDIUM"
    assert "opening_price_timestamp" in payload


def test_track_nested_last_price_without_truthy_ob_still_promotes(tmp_path: Path) -> None:
    """Promotion reads order_book dict even if last_price attribute is weird."""
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _obs(repository)

    class NestedOnly:
        def fetch_snapshot(self, ticker):
            return SimpleNamespace(
                last_price=0,  # falsy — must still promote from to_dict
                to_dict=lambda: {"last_price": 99.5},
            )

    OpeningTrackUseCase(
        Browser(),
        repository=repository,
        order_book_provider=NestedOnly(),
    ).execute(
        OpeningTrackRequest(
            observation_ids_by_ticker={"BBCA": observation.observation_id},
            force=True,
        )
    )
    payload = repository.list_track_snapshots(observation.observation_id)[0].snapshot_payload
    assert payload["opening_price"] == 99.5


def test_track_mid_only_marks_missing_open(tmp_path: Path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _obs(repository)

    OpeningTrackUseCase(
        Browser(),
        repository=repository,
        order_book_provider=OrderBookMidOnly(),
    ).execute(
        OpeningTrackRequest(
            observation_ids_by_ticker={"BBCA": observation.observation_id},
            force=True,
        )
    )
    payload = repository.list_track_snapshots(observation.observation_id)[0].snapshot_payload
    assert "opening_price" not in payload
    assert payload.get("opening_price_status") == "MISSING"
