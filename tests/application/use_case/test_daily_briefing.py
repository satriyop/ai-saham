"""Tests for DailyBriefingUseCase."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.accumulation_screen_use_case import AccumulationScreenUseCase
from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingRequest,
    DailyBriefingUseCase,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    SpyCandidateObservationsRepository,
    _candle,
    _summary,
    _weekdays,
)


def test_daily_briefing_rolls_back_weekends():
    market_repo = MagicMock()
    market_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    regime_uc.execute.return_value = None

    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    # Mocking date.today() via patch of daily_briefing's imported date class
    with patch("src.application.use_case.daily_briefing_use_case.date") as mock_date:
        # Saturday, June 20, 2026
        mock_date.today.return_value = date(2026, 6, 20)
        # Ensure side_effect allows creating new date instances in the code
        mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

        response = use_case.execute(DailyBriefingRequest(as_of_date=None))
        # Should roll back Saturday to Friday, June 19, 2026
        assert response.as_of_date == date(2026, 6, 19)

        # Sunday, June 21, 2026
        mock_date.today.return_value = date(2026, 6, 21)
        response = use_case.execute(DailyBriefingRequest(as_of_date=None))
        # Should roll back Sunday to Friday, June 19, 2026
        assert response.as_of_date == date(2026, 6, 19)


def test_daily_briefing_writes_zero_candidate_observations(monkeypatch):
    """S1 regression: DailyBriefingUseCase calls AccumulationScreenUseCase.execute()
    directly, which is read-only — it must never persist observations even with
    a real screen use case wired to a live observations repository."""
    from src.application.use_case import daily_briefing_use_case as module

    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    spy_repo = SpyCandidateObservationsRepository()

    real_accum_uc = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        candidate_observations_repository=spy_repo,
    )

    monkeypatch.setattr(module, "load_universe", lambda *a, **kw: ["BBCA"])

    market_repo = MagicMock()
    market_repo.get_date_range.return_value = (as_of, as_of)
    regime_uc = MagicMock()
    regime_uc.evaluate.return_value = None

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=real_accum_uc,
        universe_loader=MagicMock(),
    )

    use_case.execute(DailyBriefingRequest(universe="lq45", as_of_date=as_of))

    assert spy_repo.saved == []
