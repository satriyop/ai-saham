from datetime import date, datetime
from unittest.mock import MagicMock

from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingRequest,
    DailyBriefingUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningObservation,
)


def test_daily_briefing_reads_pre_open_snapshot_from_learning_repository(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *args, **kwargs: ["BBCA"],
    )
    day = date(2026, 6, 19)
    observation = LearningObservation.create(
        purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        policy_contract="pre_open_directional_baseline.v1",
        horizon_contract="open_30m",
        compatibility_id="cohort",
        cutoff_at=datetime(2026, 6, 19, 8, 57, tzinfo=IDX_TIMEZONE),
        universe_id="iev:2026-06-19",
        window_id="BBCA:2026-06-19",
        decision_payload={
            "ticker": "BBCA",
            "candidate": {"iev": 10_000, "iep": 10_050, "trend": "UP"},
            "trade_setup": {"action": "ENTER"},
        },
        captured_at=datetime(2026, 6, 19, 8, 57, tzinfo=IDX_TIMEZONE),
    )
    learning_repository = MagicMock()
    learning_repository.list_observations.return_value = [observation]
    market_repository = MagicMock()
    market_repository.get_date_range.return_value = None
    market_repository.get_candles.return_value = []
    broker_repository = MagicMock()
    broker_repository.get_date_range.return_value = None
    accumulation = MagicMock()
    accumulation.execute.return_value = MagicMock(candidates=[])

    response = DailyBriefingUseCase(
        market_repository=market_repository,
        broker_repository=broker_repository,
        regime_use_case=MagicMock(),
        accumulation_use_case=accumulation,
        universe_loader=MagicMock(),
        learning_observation_repository=learning_repository,
    ).execute(DailyBriefingRequest(as_of_date=day))

    assert response.opening_snapshot_date == day
    assert response.opening_candidates[0].ticker == "BBCA"
    assert response.opening_candidates[0].opening_setup == "ENTER"
    learning_repository.list_observations.assert_called_once_with(
        AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
    )
