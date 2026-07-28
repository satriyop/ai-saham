"""ADR-052 Commit 3: corporate-action calendar section of the daily briefing."""

from datetime import date, timedelta
from unittest.mock import MagicMock

from src.application.use_case.daily_briefing_use_case import (
    CORP_ACTION_LOOKAHEAD_DAYS,
    DailyBriefingRequest,
    DailyBriefingUseCase,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)


class _FakeUniverseCorpActionRepo:
    """Fake implementing only get_events_for_universe (the briefing's dependency)."""

    def __init__(self, events):
        self._events = events
        self.calls = []

    def get_events_for_universe(
        self, tickers, from_date, to_date, event_types=None, as_of_fetched_at=None
    ):
        self.calls.append((tickers, from_date, to_date))
        return list(self._events)


def _event(ticker, event_type, date_role, event_date, note=None):
    return CorporateActionCalendarEvent(
        event_type=event_type,
        source_event_id=f"{ticker}-{date_role.value}-{event_date.isoformat()}",
        ticker=ticker,
        dates=(CorporateActionCalendarDate(date_role=date_role, event_date=event_date),),
        event_note=note,
    )


def _build_use_case(monkeypatch, corp_repo, tickers=("ICBP",)):
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *args, **kwargs: list(tickers),
    )
    market_repository = MagicMock()
    market_repository.get_date_range.return_value = None
    market_repository.get_candles.return_value = []
    broker_repository = MagicMock()
    broker_repository.get_date_range.return_value = None
    accumulation = MagicMock()
    accumulation.execute.return_value = MagicMock(candidates=[])
    learning = MagicMock()
    learning.list_observations.return_value = []
    return DailyBriefingUseCase(
        market_repository=market_repository,
        broker_repository=broker_repository,
        regime_use_case=MagicMock(),
        accumulation_use_case=accumulation,
        universe_loader=MagicMock(),
        learning_observation_repository=learning,
        corp_action_repository=corp_repo,
    )


def test_corp_actions_flatten_sort_and_window(monkeypatch):
    day = date(2026, 6, 19)
    tomorrow = day + timedelta(days=1)
    in_window = day + timedelta(days=10)
    out_window = day + timedelta(days=CORP_ACTION_LOOKAHEAD_DAYS + 5)

    events = [
        _event("ICBP", CorporateActionType.DIVIDEND, CorporateActionDateRole.PAYMENT_DATE, day),
        _event("BRPT", CorporateActionType.DIVIDEND, CorporateActionDateRole.EX_DATE, in_window),
        _event("INDF", CorporateActionType.DIVIDEND, CorporateActionDateRole.CUM_DATE, tomorrow),
        # Outside the 14d window → must be dropped.
        _event("AKRA", CorporateActionType.RUPS, CorporateActionDateRole.RUPS_DATE, out_window),
    ]
    repo = _FakeUniverseCorpActionRepo(events)
    uc = _build_use_case(monkeypatch, repo, tickers=("ICBP", "BRPT", "INDF", "AKRA"))

    response = uc.execute(DailyBriefingRequest(as_of_date=day))
    rows = response.upcoming_corp_actions

    # AKRA (out of window) dropped; remaining sorted by (date, ticker).
    assert [r.ticker for r in rows] == ["ICBP", "INDF", "BRPT"]
    assert rows[0].event_date == day
    assert rows[0].event_type == "dividend"
    assert rows[0].date_role == "payment_date"
    # Repo queried with the forward window.
    tickers_arg, from_arg, to_arg = repo.calls[0]
    assert from_arg == day
    assert to_arg == day + timedelta(days=CORP_ACTION_LOOKAHEAD_DAYS)


def test_corp_actions_empty_when_no_repo(monkeypatch):
    monkeypatch.setattr(
        "src.application.use_case.daily_briefing_use_case.load_universe",
        lambda *args, **kwargs: ["ICBP"],
    )
    market_repository = MagicMock()
    market_repository.get_date_range.return_value = None
    market_repository.get_candles.return_value = []
    broker_repository = MagicMock()
    broker_repository.get_date_range.return_value = None
    accumulation = MagicMock()
    accumulation.execute.return_value = MagicMock(candidates=[])
    learning = MagicMock()
    learning.list_observations.return_value = []
    uc = DailyBriefingUseCase(
        market_repository=market_repository,
        broker_repository=broker_repository,
        regime_use_case=MagicMock(),
        accumulation_use_case=accumulation,
        universe_loader=MagicMock(),
        learning_observation_repository=learning,
        # corp_action_repository omitted → no calendar section.
    )
    response = uc.execute(DailyBriefingRequest(as_of_date=date(2026, 6, 19)))
    assert response.upcoming_corp_actions == []
