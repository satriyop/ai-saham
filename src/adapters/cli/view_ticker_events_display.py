"""
Corporate actions and news sentiment panels for ticker dashboard.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date

from rich.text import Text

from src.adapters.cli.rich_display import compact_table, panel
from src.adapters.cli.view_ticker_formatters import _empty_state_text, _not_cached
from src.adapters.cli.view_ticker_status import CacheStatus
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
)
from src.domain.value_objects.corporate_action_event import CorporateActionEvent

# Dashboard shows recent history + near-term upcoming, not only "next 180d".
CORP_ACTION_LOOKBACK_DAYS = 365
CORP_ACTION_LOOKAHEAD_DAYS = 180
CORP_ACTION_PANEL_TITLE = "Corporate Actions (12m)"


def _calendar_event_to_display(event: CorporateActionCalendarEvent) -> CorporateActionEvent:
    """Map market-wide calendar event into the ticker-dashboard display shape."""
    by_role = {d.date_role: d.event_date for d in event.dates}

    detail = ""
    if event.amount_value:
        if event.amount_currency and "IDR" in event.amount_currency.upper():
            detail = f"Rp {event.amount_value}"
        else:
            detail = str(event.amount_value)
    elif event.ratio_old and event.ratio_new:
        detail = f"{event.ratio_old}:{event.ratio_new}"
    if event.event_note:
        detail = f"{detail} · {event.event_note}".strip(" ·") if detail else event.event_note

    return CorporateActionEvent(
        ticker=event.ticker,
        event_type=event.event_type.value,
        ex_date=by_role.get(CorporateActionDateRole.EX_DATE),
        cum_date=by_role.get(CorporateActionDateRole.CUM_DATE),
        record_date=by_role.get(CorporateActionDateRole.RECORDING_DATE),
        payment_date=by_role.get(CorporateActionDateRole.PAYMENT_DATE),
        announcement_date=None,
        detail=detail,
        status="active" if event.active else "completed",
    )


def _merge_corp_action_events(
    *event_lists: list[CorporateActionEvent],
) -> list[CorporateActionEvent]:
    """Dedupe ticker-cache + calendar events for display (newest first)."""
    seen: set[tuple] = set()
    merged: list[CorporateActionEvent] = []
    for events in event_lists:
        for event in events:
            if event.event_type == "__NONE__":
                continue
            key = (
                event.event_type.upper(),
                event.ex_date,
                event.cum_date,
                event.record_date,
                event.payment_date,
                (event.detail or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)

    return sorted(
        merged,
        key=lambda e: (
            e.ex_date or e.cum_date or e.record_date or e.announcement_date or date.min
        ),
        reverse=True,
    )


def _corp_action_panel(
    events: list,
    *,
    status: CacheStatus = CacheStatus.EMPTY,
    last_known=None,
    empty_hint: str | None = None,
) -> object:
    events_sorted = [e for e in events if getattr(e, "event_type", None) != "__NONE__"]
    if not events_sorted:
        return panel(
            _empty_state_text(
                status,
                window_label="last 12 months",
                last_known=last_known,
                hint=empty_hint,
            ),
            title=CORP_ACTION_PANEL_TITLE,
        )

    tbl = compact_table()
    tbl.add_column("Type", style="dim", min_width=10)
    tbl.add_column("Ex-date", min_width=11)
    tbl.add_column("Cum", min_width=11, style="dim")
    tbl.add_column("Detail")
    tbl.add_column("Status", min_width=8)

    for e in events_sorted[:8]:
        status_style = "green" if e.status == "active" else "dim"
        tbl.add_row(
            e.event_type.replace("_", " ").title(),
            str(e.ex_date) if e.ex_date else "\u2014",
            str(e.cum_date) if e.cum_date else "\u2014",
            e.detail or "\u2014",
            Text(e.status or "\u2014", style=status_style),
        )

    return panel(tbl, title=CORP_ACTION_PANEL_TITLE)


def _sentiment_panel(logs: list, *, empty_hint: str | None = None) -> object:
    if not logs:
        return panel(_not_cached(hint=empty_hint), title="News Sentiment")

    tbl = compact_table()
    tbl.add_column("Date", style="dim", min_width=11)
    tbl.add_column("Sentiment", min_width=10)
    tbl.add_column("Catalyst", style="dim")
    tbl.add_column("Score", justify="right", min_width=5, style="dim")

    _SENTIMENT_STYLE = {"POSITIVE": "green", "NEGATIVE": "red", "NEUTRAL": "yellow"}

    for log in logs[:8]:
        style = _SENTIMENT_STYLE.get(log.sentiment.value, "default")
        tbl.add_row(
            str(log.date),
            Text(log.sentiment.value.title(), style=style),
            log.catalyst.value.replace("_", " ").title() if log.catalyst else "\u2014",
            f"{log.score:.2f}",
        )

    return panel(tbl, title="News Sentiment")
