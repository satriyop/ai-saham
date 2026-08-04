"""Offline agent tests for get_ticker_corporate_actions (ADR-061 closed read tool)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pytest

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolExecutionStatus,
    AgentToolName,
    AgentToolSideEffect,
)
from src.application.services.agent_accumulation_context import (
    build_agent_accumulation_context,
)
from src.application.services.agent_ticker_corporate_actions_tool import (
    CorpActionEventData,
    TickerCorporateActionsArguments,
    TickerCorporateActionsResultData,
    TickerCorporateActionsTool,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from tests.application.services.test_agent_accumulation_context import make_candidate

pytestmark = pytest.mark.agent

_TODAY = date.today()


def _context() -> AgentToolExecutionContext:
    return AgentToolExecutionContext(build_agent_accumulation_context(make_candidate()))


def _cadate(
    role: CorporateActionDateRole, event_date: date, event_time: str | None = None
) -> CorporateActionCalendarDate:
    return CorporateActionCalendarDate(date_role=role, event_date=event_date, event_time=event_time)


def _event(
    event_type: CorporateActionType,
    source_event_id: str,
    dates: tuple[CorporateActionCalendarDate, ...],
    *,
    company_name: str | None = "BANK CENTRAL ASIA",
    active: bool = True,
    amount_value: str | None = None,
) -> CorporateActionCalendarEvent:
    return CorporateActionCalendarEvent(
        event_type=event_type,
        source_event_id=source_event_id,
        ticker="BBCA",
        dates=dates,
        company_name=company_name,
        active=active,
        amount_value=amount_value,
    )


@dataclass
class _FakeRepo:
    events: list[CorporateActionCalendarEvent]
    calls: list[tuple[str, date, date]] = field(default_factory=list)
    raises: bool = False

    def get_events_for_ticker(
        self, ticker: str, from_date: date, to_date: date
    ) -> list[CorporateActionCalendarEvent]:
        self.calls.append((ticker, from_date, to_date))
        if self.raises:
            raise RuntimeError("boom")
        return list(self.events)


def _find(events: tuple[CorpActionEventData, ...], event_type: str) -> CorpActionEventData:
    for ev in events:
        if ev.event_type == event_type:
            return ev
    raise AssertionError(f"event_type {event_type!r} not found")


def test_definition_is_closed_read_none_approval() -> None:
    tool = TickerCorporateActionsTool(_FakeRepo([]))
    assert tool.definition.name is AgentToolName.GET_TICKER_CORPORATE_ACTIONS
    assert tool.definition.side_effect is AgentToolSideEffect.NONE
    assert tool.definition.approval.value == "NONE"
    assert (
        "score" not in tool.definition.description.lower()
        or "not a" in tool.definition.description.lower()
    )


def test_happy_path_splits_upcoming_and_recent() -> None:
    upcoming_event = _event(
        CorporateActionType.RUPS,
        "rups-1",
        (_cadate(CorporateActionDateRole.RUPS_DATE, _TODAY + timedelta(days=20)),),
    )
    recent_event = _event(
        CorporateActionType.DIVIDEND,
        "div-past",
        (_cadate(CorporateActionDateRole.PAYMENT_DATE, _TODAY - timedelta(days=15)),),
        amount_value="55",
    )
    fake = _FakeRepo([recent_event, upcoming_event])
    tool = TickerCorporateActionsTool(fake)

    out = tool.execute("ca-1", TickerCorporateActionsArguments("BBCA", 90, 20), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(out.data, TickerCorporateActionsResultData)
    assert out.data.ticker == "BBCA"
    assert out.data.event_count == 2
    assert len(out.data.upcoming) == 1
    assert len(out.data.recent) == 1
    assert out.data.upcoming[0].event_type == "rups"
    assert out.data.recent[0].event_type == "dividend"
    assert out.data.as_of == _TODAY
    assert out.provenance.source == "ticker-corp-action-calendar-cache"
    assert out.freshness is not None and out.freshness.as_of == _TODAY
    # symmetric window range reaches the repository
    assert fake.calls == [("BBCA", _TODAY - timedelta(days=90), _TODAY + timedelta(days=90))]


def test_rups_only_event_carries_its_rups_date() -> None:
    # Regression: the 5-field dashboard flatten silently DROPS rups_date. The
    # role-keyed projection must surface it.
    event = _event(
        CorporateActionType.RUPS,
        "rups-only",
        (_cadate(CorporateActionDateRole.RUPS_DATE, _TODAY + timedelta(days=12), "10:00"),),
    )
    tool = TickerCorporateActionsTool(_FakeRepo([event]))
    out = tool.execute("ca-rups", TickerCorporateActionsArguments("BBCA", 90, 20), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert isinstance(out.data, TickerCorporateActionsResultData)
    rups = _find(out.data.upcoming, "rups")
    assert len(rups.dates) == 1
    assert rups.dates[0].role == "rups_date"
    assert rups.dates[0].event_date == _TODAY + timedelta(days=12)
    assert rups.dates[0].event_time == "10:00"
    assert "NO_DATED_MILESTONES" not in out.warnings


def test_dividend_event_carries_all_four_dates_sorted() -> None:
    event = _event(
        CorporateActionType.DIVIDEND,
        "div-full",
        (
            _cadate(CorporateActionDateRole.PAYMENT_DATE, _TODAY + timedelta(days=12)),
            _cadate(CorporateActionDateRole.EX_DATE, _TODAY + timedelta(days=5)),
            _cadate(CorporateActionDateRole.RECORDING_DATE, _TODAY + timedelta(days=6)),
            _cadate(CorporateActionDateRole.CUM_DATE, _TODAY + timedelta(days=4)),
        ),
        amount_value="120",
    )
    tool = TickerCorporateActionsTool(_FakeRepo([event]))
    out = tool.execute("ca-div", TickerCorporateActionsArguments("BBCA", 90, 20), _context())

    assert isinstance(out.data, TickerCorporateActionsResultData)
    div = _find(out.data.upcoming, "dividend")
    roles = [d.role for d in div.dates]
    assert roles == ["cum_date", "ex_date", "recording_date", "payment_date"]
    assert div.amount_value == "120"


def test_window_days_and_limit_caps_are_enforced_not_rejected() -> None:
    tool = TickerCorporateActionsTool(_FakeRepo([]))
    args = tool.build_arguments(("bbca", "9999", "999"))
    assert args.ticker == "BBCA"
    assert args.window_days == 365
    assert args.limit == 40

    defaults = tool.build_arguments(("BBCA", "", ""))
    assert defaults.window_days == 90
    assert defaults.limit == 20


def test_argument_validation_rejects_bad_inputs() -> None:
    tool = TickerCorporateActionsTool(_FakeRepo([]))
    with pytest.raises(ValueError):
        tool.build_arguments(("TOO_LONG", "", ""))
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", "0", ""))
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", "", "0"))
    with pytest.raises(ValueError):
        tool.build_arguments(("BBCA", ""))


def test_limit_caps_combined_event_count_keeping_closest() -> None:
    near_up = _event(
        CorporateActionType.RUPS,
        "near-up",
        (_cadate(CorporateActionDateRole.RUPS_DATE, _TODAY + timedelta(days=1)),),
    )
    near_up2 = _event(
        CorporateActionType.PUBEX,
        "near-up2",
        (_cadate(CorporateActionDateRole.PUBEX_DATE, _TODAY + timedelta(days=2)),),
    )
    far_recent = _event(
        CorporateActionType.DIVIDEND,
        "far-recent",
        (_cadate(CorporateActionDateRole.PAYMENT_DATE, _TODAY - timedelta(days=100)),),
    )
    tool = TickerCorporateActionsTool(_FakeRepo([far_recent, near_up, near_up2]))
    out = tool.execute("ca-cap", TickerCorporateActionsArguments("BBCA", 365, 2), _context())

    assert isinstance(out.data, TickerCorporateActionsResultData)
    assert out.data.event_count == 2
    kept = {ev.event_type for ev in out.data.upcoming + out.data.recent}
    assert kept == {"rups", "pubex"}


def test_empty_repository_result_is_unavailable() -> None:
    tool = TickerCorporateActionsTool(_FakeRepo([]))
    out = tool.execute("ca-miss", TickerCorporateActionsArguments("BBCA", 90, 20), _context())
    assert out.status is AgentToolExecutionStatus.UNAVAILABLE
    assert out.data is None
    assert out.error_code == "TICKER_CORP_ACTIONS_UNAVAILABLE"


def test_zero_dates_event_is_success_with_info_warning() -> None:
    dateless = _event(CorporateActionType.IPO, "ipo-nodate", ())
    tool = TickerCorporateActionsTool(_FakeRepo([dateless]))
    out = tool.execute("ca-nodate", TickerCorporateActionsArguments("BBCA", 90, 20), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert "NO_DATED_MILESTONES" in out.warnings
    assert isinstance(out.data, TickerCorporateActionsResultData)
    # Dateless events are not actionable "upcoming" — they bucket into recent.
    assert out.data.upcoming == ()
    assert len(out.data.recent) == 1
    assert out.data.recent[0].dates == ()


def test_repository_exception_is_failed() -> None:
    tool = TickerCorporateActionsTool(_FakeRepo([], raises=True))
    out = tool.execute("ca-fail", TickerCorporateActionsArguments("BBCA", 90, 20), _context())
    assert out.status is AgentToolExecutionStatus.FAILED
    assert out.data is None
    assert out.error_code == "TICKER_CORP_ACTIONS_READ_FAILED"
    assert out.retryable is False


def test_result_fits_byte_cap_and_is_frozen_typed() -> None:
    events = [
        _event(
            CorporateActionType.DIVIDEND,
            f"div-{i}",
            (_cadate(CorporateActionDateRole.EX_DATE, _TODAY + timedelta(days=i)),),
            amount_value=str(i),
        )
        for i in range(1, 41)
    ]
    tool = TickerCorporateActionsTool(_FakeRepo(events))
    out = tool.execute("ca-cap", TickerCorporateActionsArguments("BBCA", 365, 40), _context())

    assert out.status is AgentToolExecutionStatus.SUCCESS
    assert out.serialized_size() <= tool.definition.max_result_bytes
    assert isinstance(out.data, TickerCorporateActionsResultData)
    assert type(out.data).__dataclass_params__.frozen is True
    assert not hasattr(out.data, "score")
    assert not hasattr(out.data, "risk")
    assert not hasattr(out.data, "verdict")
