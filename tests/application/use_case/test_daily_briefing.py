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

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    regime_uc.execute.return_value = None

    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
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
        assert response.live_session_date == date(2026, 6, 19)
        assert response.is_historical is False

        # Sunday, June 21, 2026
        mock_date.today.return_value = date(2026, 6, 21)
        response = use_case.execute(DailyBriefingRequest(as_of_date=None))
        # Should roll back Sunday to Friday, June 19, 2026
        assert response.live_session_date == date(2026, 6, 19)
        assert response.is_historical is False


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
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (as_of, as_of)
    regime_uc = MagicMock()
    regime_uc.evaluate.return_value = None

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=real_accum_uc,
        universe_loader=MagicMock(),
    )

    use_case.execute(DailyBriefingRequest(universe="lq45", as_of_date=as_of))

    assert spy_repo.saved == []


def test_daily_briefing_historical_mode(monkeypatch):
    market_repo = MagicMock()
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: ["BBCA"],
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert response.is_historical is True
    assert response.live_session_date == date(2026, 6, 19)
    assert response.latest_completed_eod_date == date(2026, 6, 19)


def test_daily_briefing_shared_freshness(monkeypatch):
    # June 19, 2026 is Friday. If expected latest EOD is 2026-06-19,
    # but candle_as_of is 2026-06-18 (older/stale).
    market_repo = MagicMock()
    market_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 18))

    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = (date(2026, 6, 1), date(2026, 6, 19))

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: ["BBCA"],
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(universe="lq45", as_of_date=date(2026, 6, 19))
    )

    assert len(response.data_freshness) == 1
    assert response.data_freshness[0].freshness.candle_state.value == "STALE"
    assert response.stale_count == 1


def test_daily_briefing_opening_snapshot(tmp_path, monkeypatch):
    import json
    opening_dir = tmp_path / "opening"
    date_dir = opening_dir / "20260619"
    date_dir.mkdir(parents=True)

    snapshot_file = date_dir / "snapshot.json"
    snapshot_data = {
        "captured_at": "2026-06-19T09:05:00+07:00",
        "candidates": [
            {"ticker": "BBCA", "opening_setup": "PRIME", "iev": 10000, "iep": 10050, "trend": "UP"}
        ]
    }
    snapshot_file.write_text(json.dumps(snapshot_data))

    market_repo = MagicMock()
    market_repo.get_date_range.return_value = None
    broker_repo = MagicMock()
    broker_repo.get_date_range.return_value = None

    regime_uc = MagicMock()
    accum_uc = MagicMock()
    accum_uc.execute.return_value = MagicMock(candidates=[])

    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *a, **kw: ["BBCA"],
    )

    use_case = DailyBriefingUseCase(
        market_repository=market_repo,
        broker_repository=broker_repo,
        regime_use_case=regime_uc,
        accumulation_use_case=accum_uc,
        universe_loader=MagicMock(),
    )

    response = use_case.execute(
        DailyBriefingRequest(
            universe="lq45",
            as_of_date=date(2026, 6, 19),
            opening_data_dir=opening_dir,
        )
    )

    assert response.opening_snapshot_date == date(2026, 6, 19)
    assert len(response.opening_candidates) == 1
    assert response.opening_candidates[0].ticker == "BBCA"
