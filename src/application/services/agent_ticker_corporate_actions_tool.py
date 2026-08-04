"""Bounded agent projection: ticker corporate action calendar (cache-only).

Projects the market-wide corporate action calendar for one ticker into upcoming
vs recent buckets. Milestone dates are projected role-keyed and lossless directly
from ``event.dates`` (every ``CorporateActionDateRole`` including ``rups_date`` and
``pubex_date``). This deliberately does NOT reuse
``ticker_dashboard_corp_actions.calendar_event_to_display()`` — that flattens to
five named date fields and silently drops RUPS/PUBEX milestones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from src.application.dto.agent_tool_context import AgentToolExecutionContext
from src.application.dto.agent_tools import (
    AgentToolArgumentField,
    AgentToolArguments,
    AgentToolDefinition,
    AgentToolExecutionResult,
    AgentToolExecutionStatus,
    AgentToolFreshness,
    AgentToolName,
    AgentToolProvenance,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarEvent,
)

_TICKER_PATTERN = re.compile(r"[A-Z]{4}")
_ARGUMENT_SCHEMA_ID = "agent_tool.ticker_corp_action.args.v1"
_RESULT_SCHEMA_ID = "agent_tool.ticker_corp_action.v1"

_DEFAULT_WINDOW_DAYS = 90
_MAX_WINDOW_DAYS = 365
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 40

_INFO_NO_DATED_MILESTONES = "NO_DATED_MILESTONES"


class _CorpActionSource(Protocol):
    def get_events_for_ticker(
        self,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> list[CorporateActionCalendarEvent]: ...


@dataclass(frozen=True)
class TickerCorporateActionsArguments(AgentToolArguments):
    ticker: str
    window_days: int
    limit: int

    def __post_init__(self) -> None:
        if _TICKER_PATTERN.fullmatch(self.ticker) is None:
            raise ValueError("ticker must be a canonical four-letter IDX symbol")
        if self.window_days < 1 or self.window_days > _MAX_WINDOW_DAYS:
            raise ValueError(f"window_days must be between 1 and {_MAX_WINDOW_DAYS}")
        if self.limit < 1 or self.limit > _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")


@dataclass(frozen=True)
class CorpActionDateData:
    role: str  # CorporateActionDateRole.value, e.g. "rups_date"
    event_date: date
    event_time: str | None


@dataclass(frozen=True)
class CorpActionEventData:
    event_type: str  # CorporateActionType.value
    dates: tuple[CorpActionDateData, ...]  # role-keyed, lossless — NOT the 5-field flatten
    amount_value: str | None
    amount_currency: str | None
    ratio_old: str | None
    ratio_new: str | None
    price: str | None
    event_note: str | None
    active: bool
    company_name: str | None


@dataclass(frozen=True)
class TickerCorporateActionsResultData:
    schema_id: str
    ticker: str
    as_of: date
    upcoming: tuple[CorpActionEventData, ...]
    recent: tuple[CorpActionEventData, ...]
    event_count: int


class TickerCorporateActionsTool:
    """Project cache-only corporate action calendar events into upcoming/recent buckets."""

    _definition = AgentToolDefinition(
        name=AgentToolName.GET_TICKER_CORPORATE_ACTIONS,
        description=(
            "Return one ticker's upcoming and recent corporate action calendar events "
            "(dividend, split, rights issue, RUPS, PUBEX, tender, IPO) with role-keyed "
            "milestone dates (ex/cum/record/payment, rups_date, pubex_date, etc.) and "
            "descriptive amount/ratio/price fields. Facts only — not a corporate-action "
            "risk score."
        ),
        argument_schema_id=_ARGUMENT_SCHEMA_ID,
        result_schema_id=_RESULT_SCHEMA_ID,
        arguments=(
            AgentToolArgumentField(
                "ticker",
                "Canonical uppercase four-letter IDX ticker, for example BBCA.",
            ),
            AgentToolArgumentField(
                "window_days",
                f"Optional symmetric look-back/look-ahead window in days "
                f"(1-{_MAX_WINDOW_DAYS}). Empty string defaults to {_DEFAULT_WINDOW_DAYS}; "
                f"values above {_MAX_WINDOW_DAYS} are capped.",
            ),
            AgentToolArgumentField(
                "limit",
                f"Optional maximum number of events (1-{_MAX_LIMIT}). Empty string "
                f"defaults to {_DEFAULT_LIMIT}; values above {_MAX_LIMIT} are capped.",
            ),
        ),
        required_context="LOCAL_TICKER_CORP_ACTION_CACHE",
        timeout_ms=3_000,
        max_result_bytes=32 * 1024,
    )

    def __init__(self, source: _CorpActionSource) -> None:
        self._source = source

    @property
    def definition(self) -> AgentToolDefinition:
        return self._definition

    def build_arguments(self, ordered_values: tuple[str, ...]) -> TickerCorporateActionsArguments:
        if len(ordered_values) != 3:
            raise ValueError("ticker corporate actions tool requires exactly three arguments")
        ticker = ordered_values[0].strip().upper()
        window_days = _parse_window_days(ordered_values[1])
        limit = _parse_limit(ordered_values[2])
        return TickerCorporateActionsArguments(ticker=ticker, window_days=window_days, limit=limit)

    def execute(
        self,
        call_id: str,
        arguments: AgentToolArguments,
        context: AgentToolExecutionContext,
    ) -> AgentToolExecutionResult:
        del context
        if not isinstance(arguments, TickerCorporateActionsArguments):
            raise TypeError("ticker corporate actions tool received the wrong argument type")
        ticker = arguments.ticker
        as_of = date.today()  # `as_of` is never a model argument — always execute-time today.
        source_reference = f"ticker-corp-actions:{ticker}:{as_of.isoformat()}"
        provenance = AgentToolProvenance(
            source="ticker-corp-action-calendar-cache",
            as_of=as_of,
            source_reference=source_reference,
        )
        from_date = as_of - timedelta(days=arguments.window_days)
        to_date = as_of + timedelta(days=arguments.window_days)
        try:
            events = self._source.get_events_for_ticker(ticker, from_date, to_date)
        except Exception:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.FAILED,
                data=None,
                error_code="TICKER_CORP_ACTIONS_READ_FAILED",
                error_message="Ticker corporate action calendar could not be read",
                provenance=provenance,
                source_reference=source_reference,
            )

        if not events:
            return AgentToolExecutionResult.create(
                call_id=call_id,
                name=self.definition.name,
                status=AgentToolExecutionStatus.UNAVAILABLE,
                data=None,
                error_code="TICKER_CORP_ACTIONS_UNAVAILABLE",
                error_message="No cached corporate action events are available for this ticker",
                provenance=provenance,
                source_reference=source_reference,
            )

        capped = _cap_events(events, as_of, arguments.limit)
        upcoming, recent = _split_events(capped, as_of)
        # Dateless events are informational only; still SUCCESS with an INFO note.
        warnings: tuple[str, ...] = ()
        if any(not event.dates for event in capped):
            warnings = (_INFO_NO_DATED_MILESTONES,)

        data = TickerCorporateActionsResultData(
            schema_id=_RESULT_SCHEMA_ID,
            ticker=ticker,
            as_of=as_of,
            upcoming=upcoming,
            recent=recent,
            event_count=len(upcoming) + len(recent),
        )
        return AgentToolExecutionResult.create(
            call_id=call_id,
            name=self.definition.name,
            status=AgentToolExecutionStatus.SUCCESS,
            data=data,
            warnings=warnings,
            freshness=AgentToolFreshness(
                as_of=as_of,
                status=AgentToolExecutionStatus.SUCCESS.value,
                warnings=warnings,
            ),
            provenance=provenance,
            source_reference=source_reference,
        )


def _primary_date(event: CorporateActionCalendarEvent) -> date | None:
    """Earliest dated milestone of an event, or None when the event is dateless."""
    if not event.dates:
        return None
    return min(d.event_date for d in event.dates)


def _event_row(event: CorporateActionCalendarEvent) -> CorpActionEventData:
    dates = tuple(
        CorpActionDateData(
            role=d.date_role.value,
            event_date=d.event_date,
            event_time=d.event_time,
        )
        for d in sorted(event.dates, key=lambda d: d.event_date)
    )
    return CorpActionEventData(
        event_type=event.event_type.value,
        dates=dates,
        amount_value=event.amount_value,
        amount_currency=event.amount_currency,
        ratio_old=event.ratio_old,
        ratio_new=event.ratio_new,
        price=event.price,
        event_note=event.event_note,
        active=event.active,
        company_name=event.company_name,
    )


def _cap_events(
    events: list[CorporateActionCalendarEvent], as_of: date, limit: int
) -> list[CorporateActionCalendarEvent]:
    """Keep the `limit` events closest to `as_of` (dateless sort last). Safer, smaller."""
    return sorted(
        events,
        key=lambda event: abs((_primary_date(event) or date.max) - as_of),
    )[:limit]


def _split_events(
    events: list[CorporateActionCalendarEvent], as_of: date
) -> tuple[tuple[CorpActionEventData, ...], tuple[CorpActionEventData, ...]]:
    """Split into upcoming (primary_date >= as_of) vs recent; dateless events are recent."""
    upcoming: list[tuple[date, CorporateActionCalendarEvent]] = []
    recent: list[tuple[date | None, CorporateActionCalendarEvent]] = []
    for event in events:
        primary = _primary_date(event)
        if primary is not None and primary >= as_of:
            upcoming.append((primary, event))
        else:
            recent.append((primary, event))
    upcoming.sort(key=lambda item: item[0])
    # Recent: descending by primary_date, dateless (None) last.
    recent.sort(
        key=lambda item: (item[0] is None, -item[0].toordinal() if item[0] is not None else 0)
    )
    upcoming_rows = tuple(_event_row(event) for _, event in upcoming)
    recent_rows = tuple(_event_row(event) for _, event in recent)
    return upcoming_rows, recent_rows


def _parse_window_days(raw: str) -> int:
    text = raw.strip()
    if not text:
        return _DEFAULT_WINDOW_DAYS
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("window_days must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"window_days must be between 1 and {_MAX_WINDOW_DAYS}")
    return min(value, _MAX_WINDOW_DAYS)


def _parse_limit(raw: str) -> int:
    text = raw.strip()
    if not text:
        return _DEFAULT_LIMIT
    try:
        value = int(text)
    except ValueError as exc:
        raise ValueError("limit must be empty or an integer") from exc
    if value < 1:
        raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
    return min(value, _MAX_LIMIT)
