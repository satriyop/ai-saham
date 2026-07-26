from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.application.use_case.database_learning_lifecycle_use_case import (
    EvaluateLearningCohortRequest,
    EvaluateLearningCohortUseCase,
    GenerateAccumulationPricePathLabelsUseCase,
    GenerateLearningLabelsRequest,
    GeneratePreOpenOutcomeLabelsUseCase,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    EvaluationReadiness,
    LearningContractError,
    LearningContractId,
    LearningObservation,
    LearningTrackSnapshot,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)

NOW = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)


def _observation(*, day: int, compatibility_id: str = "compat-1") -> LearningObservation:
    at = datetime(2026, 7, day, 1, 0, tzinfo=timezone.utc)
    return LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id=compatibility_id,
        cutoff_at=at,
        universe_id="iev",
        window_id=f"BBCA:2026-07-{day:02d}",
        decision_payload={"ticker": "BBCA", "screen_result": "PASS"},
        captured_at=at,
    )


def test_pre_open_evaluation_reads_persisted_labels_without_track_reread(
    tmp_path,
) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observations = [_observation(day=26), _observation(day=27)]
    for observation in observations:
        repository.add_observation(observation)
        repository.add_track_snapshot(
            LearningTrackSnapshot.create(
                observation_id=observation.observation_id,
                sampled_at=observation.cutoff_at,
                source="stockbit.opening_track",
                snapshot_payload={"mid_price": 100.0},
                captured_at=observation.cutoff_at,
            )
        )
        repository.add_track_snapshot(
            LearningTrackSnapshot.create(
                observation_id=observation.observation_id,
                sampled_at=observation.cutoff_at.replace(minute=30),
                source="stockbit.opening_track",
                snapshot_payload={"mid_price": 101.0},
                captured_at=observation.cutoff_at.replace(minute=30),
            )
        )
    generator = GeneratePreOpenOutcomeLabelsUseCase(
        observations=repository,
        tracks=repository,
        labels=repository,
    )
    generator.execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            compatibility_id="compat-1",
            label_contract=LearningContractId.PRE_OPEN_LABEL,
            labeled_at=NOW,
        )
    )

    class TrackRejectingRepository:
        def __getattr__(self, name):
            if name == "list_track_snapshots":
                raise AssertionError("evaluation must not reread tracks")
            return getattr(repository, name)

    evaluation = EvaluateLearningCohortUseCase(
        observations=TrackRejectingRepository(),
        labels=TrackRejectingRepository(),
        evaluations=TrackRejectingRepository(),
    ).execute(
        EvaluateLearningCohortRequest(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            compatibility_id="compat-1",
            evaluated_at=NOW,
        )
    )

    assert evaluation.readiness is EvaluationReadiness.OOS_DIAGNOSTIC_READY
    assert evaluation.metrics["available_count"] == 2


def test_one_session_pre_open_evaluation_is_descriptive(tmp_path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _observation(day=27)
    repository.add_observation(observation)
    repository.add_track_snapshot(
        LearningTrackSnapshot.create(
            observation_id=observation.observation_id,
            sampled_at=NOW,
            source="stockbit.opening_track",
            snapshot_payload={"mid_price": 100.0},
            captured_at=NOW,
        )
    )
    GeneratePreOpenOutcomeLabelsUseCase(
        observations=repository,
        tracks=repository,
        labels=repository,
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            compatibility_id="compat-1",
            label_contract=LearningContractId.PRE_OPEN_LABEL,
            labeled_at=NOW,
        )
    )

    evaluation = EvaluateLearningCohortUseCase(
        observations=repository,
        labels=repository,
        evaluations=repository,
    ).execute(
        EvaluateLearningCohortRequest(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            compatibility_id="compat-1",
            evaluated_at=NOW,
        )
    )

    assert evaluation.readiness is EvaluationReadiness.DESCRIPTIVE_READY


def test_evaluation_fails_closed_for_missing_labels(tmp_path) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    repository.add_observation(_observation(day=27))

    with pytest.raises(LearningContractError, match="no persisted labels"):
        EvaluateLearningCohortUseCase(
            observations=repository,
            labels=repository,
            evaluations=repository,
        ).execute(
            EvaluateLearningCohortRequest(
                purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
                compatibility_id="compat-1",
                evaluated_at=NOW,
            )
        )


def test_accumulation_price_path_labels_preserve_corporate_action_guard(
    tmp_path,
) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_20d",
        compatibility_id="compat-1",
        cutoff_at=NOW,
        universe_id="idx30",
        window_id="BBCA:2026-07-27:20",
        decision_payload={
            "ticker": "BBCA",
            "candidate": {"entry_price": 100},
            "screen_result": "pass",
        },
        captured_at=NOW,
    )
    repository.add_observation(observation)

    class Market:
        def get_candles(self, ticker, start_date=None, end_date=None):
            return [
                Candle(
                    ticker=ticker,
                    date=date(2026, 7, 27) + timedelta(days=index),
                    open=Decimal("100"),
                    high=Decimal("102"),
                    low=Decimal("99"),
                    close=Decimal("101"),
                    volume=100,
                )
                for index in range(1, 21)
            ]

    class CorporateActions:
        def has_any_sync_marker(self):
            return False

        def get_events_for_ticker(self, *args, **kwargs):
            raise AssertionError("coverage gate must fail before event query")

    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repository,
        labels=repository,
        market_data=Market(),
        corporate_actions=CorporateActions(),
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id="compat-1",
            label_contract=LearningContractId.ACCUMULATION_LABEL,
            labeled_at=NOW,
        )
    )

    assert result.unavailable_count == 1
    assert (
        result.labels[0].metrics["unavailable_reason"]
        == "corporate_action_coverage_unavailable"
    )
