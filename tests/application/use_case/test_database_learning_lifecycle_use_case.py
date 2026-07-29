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


def test_pre_open_labels_skip_missing_tracks_then_insert_when_ready(tmp_path) -> None:
    """no_track_prices is provisional — do not lock UNAVAILABLE forever."""
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    observation = _observation(day=27)
    repository.add_observation(observation)

    first = GeneratePreOpenOutcomeLabelsUseCase(
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
    assert first.skipped_count == 1
    assert first.inserted_count == 0
    assert first.labels == ()
    assert repository.list_labels([observation.observation_id]) == ()

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

    later = GeneratePreOpenOutcomeLabelsUseCase(
        observations=repository,
        tracks=repository,
        labels=repository,
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            compatibility_id="compat-1",
            label_contract=LearningContractId.PRE_OPEN_LABEL,
            labeled_at=NOW + timedelta(hours=1),
        )
    )
    assert later.inserted_count == 1
    assert later.skipped_count == 0
    assert later.labels[0].availability.value == "AVAILABLE"
    assert later.labels[0].outcome in {"SUCCESS", "FAILURE", "NEUTRAL"}

    # Re-run must not conflict on labeled_at; already labeled → skip.
    rerun = GeneratePreOpenOutcomeLabelsUseCase(
        observations=repository,
        tracks=repository,
        labels=repository,
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            compatibility_id="compat-1",
            label_contract=LearningContractId.PRE_OPEN_LABEL,
            labeled_at=NOW + timedelta(hours=2),
        )
    )
    assert rerun.inserted_count == 0
    assert rerun.skipped_count == 1
    assert len(repository.list_labels([observation.observation_id])) == 1


def test_pre_open_labels_do_not_block_cohort_when_some_obs_untracked(
    tmp_path,
) -> None:
    """Untracked obs are skipped; tracked peers still get AVAILABLE labels."""
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    bare = _observation(day=26)
    ready = _observation(day=27)
    repository.add_observation(bare)
    repository.add_observation(ready)
    repository.add_track_snapshot(
        LearningTrackSnapshot.create(
            observation_id=ready.observation_id,
            sampled_at=ready.cutoff_at,
            source="stockbit.opening_track",
            snapshot_payload={"opening_price": 200.0},
            captured_at=ready.cutoff_at,
        )
    )
    repository.add_track_snapshot(
        LearningTrackSnapshot.create(
            observation_id=ready.observation_id,
            sampled_at=ready.cutoff_at.replace(minute=30),
            source="stockbit.opening_track",
            snapshot_payload={"mid_price": 201.0},
            captured_at=ready.cutoff_at.replace(minute=30),
        )
    )

    result = GeneratePreOpenOutcomeLabelsUseCase(
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
    assert result.observation_count == 2
    assert result.skipped_count == 1
    assert result.inserted_count == 1
    assert result.labels[0].observation_id == ready.observation_id
    assert result.labels[0].availability.value == "AVAILABLE"


def _accum_observation(
    *,
    current_price: object = "100",
    day: int = 27,
    compatibility_id: str = "compat-1",
) -> LearningObservation:
    at = datetime(2026, 7, day, 1, 0, tzinfo=timezone.utc)
    candidate: dict = {}
    if current_price is not None:
        candidate["current_price"] = current_price
    return LearningObservation.create(
        purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
        policy_contract="accumulation_discovery.policy.v1",
        horizon_contract="accum_20d",
        compatibility_id=compatibility_id,
        cutoff_at=at,
        universe_id="idx30",
        window_id=f"BBCA:2026-07-{day:02d}:20",
        decision_payload={
            "ticker": "BBCA",
            "candidate": candidate,
            "screen_result": "pass",
        },
        captured_at=at,
    )


def _forward_candles(ticker: str, signal_day: date, count: int) -> list[Candle]:
    return [
        Candle(
            ticker=ticker,
            date=signal_day + timedelta(days=index),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=100,
        )
        for index in range(1, count + 1)
    ]


class _CoveredCorporateActions:
    def has_any_sync_marker(self):
        return True

    def get_events_for_ticker(self, *args, **kwargs):
        return ()


def test_accumulation_price_path_skips_when_corporate_action_coverage_missing(
    tmp_path,
) -> None:
    """Missing calendar coverage is provisional: no label row is written."""
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    repository.add_observation(_accum_observation(current_price="100"))

    class Market:
        def get_candles(self, ticker, start_date=None, end_date=None):
            return _forward_candles(ticker, date(2026, 7, 27), 20)

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

    assert result.observation_count == 1
    assert result.skipped_count == 1
    assert result.inserted_count == 0
    assert result.unavailable_count == 0
    assert result.labels == ()
    obs_id = repository.list_observations(AssessmentPurpose.ACCUMULATION_DISCOVERY)[
        0
    ].observation_id
    assert repository.list_labels([obs_id]) == ()


def test_accumulation_price_path_uses_candidate_current_price_as_entry(
    tmp_path,
) -> None:
    """Production capture freezes candidate.current_price (session close)."""
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    repository.add_observation(_accum_observation(current_price="1000"))

    class Market:
        def get_candles(self, ticker, start_date=None, end_date=None):
            return _forward_candles(ticker, date(2026, 7, 27), 20)

    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repository,
        labels=repository,
        market_data=Market(),
        corporate_actions=_CoveredCorporateActions(),
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id="compat-1",
            label_contract=LearningContractId.ACCUMULATION_LABEL,
            labeled_at=NOW,
        )
    )

    assert result.skipped_count == 0
    assert result.inserted_count == 1
    assert result.unavailable_count == 0
    assert len(result.labels) == 1
    assert result.labels[0].availability.value == "AVAILABLE"
    assert result.labels[0].metrics["entry_reference_price"] == 1000.0


def test_accumulation_price_path_skips_incomplete_forward_window(
    tmp_path,
) -> None:
    """Incomplete horizon must not permanently lock an UNAVAILABLE row."""
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    repository.add_observation(_accum_observation(current_price="100"))

    class Market:
        def get_candles(self, ticker, start_date=None, end_date=None):
            return _forward_candles(ticker, date(2026, 7, 27), 5)

    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repository,
        labels=repository,
        market_data=Market(),
        corporate_actions=_CoveredCorporateActions(),
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id="compat-1",
            label_contract=LearningContractId.ACCUMULATION_LABEL,
            labeled_at=NOW,
        )
    )

    assert result.skipped_count == 1
    assert result.inserted_count == 0
    assert result.labels == ()
    obs_id = repository.list_observations(AssessmentPurpose.ACCUMULATION_DISCOVERY)[
        0
    ].observation_id
    assert repository.list_labels([obs_id]) == ()

    # Later run with full horizon can insert AVAILABLE (no immutable conflict).
    class FullMarket:
        def get_candles(self, ticker, start_date=None, end_date=None):
            return _forward_candles(ticker, date(2026, 7, 27), 20)

    later = GenerateAccumulationPricePathLabelsUseCase(
        observations=repository,
        labels=repository,
        market_data=FullMarket(),
        corporate_actions=_CoveredCorporateActions(),
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id="compat-1",
            label_contract=LearningContractId.ACCUMULATION_LABEL,
            labeled_at=NOW,
        )
    )
    assert later.inserted_count == 1
    assert later.labels[0].availability.value == "AVAILABLE"


def test_accumulation_price_path_skips_missing_current_price(
    tmp_path,
) -> None:
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    repository.add_observation(_accum_observation(current_price=None))

    class Market:
        def get_candles(self, ticker, start_date=None, end_date=None):
            return _forward_candles(ticker, date(2026, 7, 27), 20)

    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repository,
        labels=repository,
        market_data=Market(),
        corporate_actions=_CoveredCorporateActions(),
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id="compat-1",
            label_contract=LearningContractId.ACCUMULATION_LABEL,
            labeled_at=NOW,
        )
    )

    assert result.skipped_count == 1
    assert result.inserted_count == 0
    assert result.labels == ()


def test_accumulation_price_path_ignores_legacy_entry_price_alias(
    tmp_path,
) -> None:
    """Only candidate.current_price is supported — not entry_price/close aliases."""
    repository = SQLiteLearningArtifactRepository(tmp_path / "data.db")
    at = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)
    repository.add_observation(
        LearningObservation.create(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            policy_contract="accumulation_discovery.policy.v1",
            horizon_contract="accum_20d",
            compatibility_id="compat-1",
            cutoff_at=at,
            universe_id="idx30",
            window_id="BBCA:2026-07-27:20",
            decision_payload={
                "ticker": "BBCA",
                "candidate": {"entry_price": 100},
                "screen_result": "pass",
            },
            captured_at=at,
        )
    )

    class Market:
        def get_candles(self, ticker, start_date=None, end_date=None):
            return _forward_candles(ticker, date(2026, 7, 27), 20)

    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repository,
        labels=repository,
        market_data=Market(),
        corporate_actions=_CoveredCorporateActions(),
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id="compat-1",
            label_contract=LearningContractId.ACCUMULATION_LABEL,
            labeled_at=NOW,
        )
    )
    assert result.skipped_count == 1
    assert result.inserted_count == 0
