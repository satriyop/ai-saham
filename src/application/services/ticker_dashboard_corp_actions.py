"""
Corporate-action merge helpers for the ticker dashboard.

Layer: Application
"""

from __future__ import annotations

from datetime import date

from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
)
from src.domain.value_objects.corporate_action_event import CorporateActionEvent


def calendar_event_to_display(event: CorporateActionCalendarEvent) -> CorporateActionEvent:
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


def merge_corp_action_events(
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
