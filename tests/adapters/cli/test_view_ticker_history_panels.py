"""Unit tests for historical corporate-action / insider panel helpers."""

from datetime import date

from src.adapters.cli.view_ticker_events_display import (
    _calendar_event_to_display,
    _merge_corp_action_events,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from src.domain.value_objects.corporate_action_event import CorporateActionEvent


def test_calendar_event_to_display_maps_dividend_dates_and_amount():
    event = CorporateActionCalendarEvent(
        event_type=CorporateActionType.DIVIDEND,
        source_event_id="117860",
        ticker="BBCA",
        dates=(
            CorporateActionCalendarDate(CorporateActionDateRole.CUM_DATE, date(2026, 6, 15)),
            CorporateActionCalendarDate(CorporateActionDateRole.EX_DATE, date(2026, 6, 17)),
            CorporateActionCalendarDate(CorporateActionDateRole.RECORDING_DATE, date(2026, 6, 18)),
            CorporateActionCalendarDate(CorporateActionDateRole.PAYMENT_DATE, date(2026, 6, 26)),
        ),
        amount_value="20",
        amount_currency="CURRENCY_IDR",
        active=False,
    )

    display = _calendar_event_to_display(event)

    assert display.ticker == "BBCA"
    assert display.event_type == "dividend"
    assert display.ex_date == date(2026, 6, 17)
    assert display.cum_date == date(2026, 6, 15)
    assert display.record_date == date(2026, 6, 18)
    assert display.payment_date == date(2026, 6, 26)
    assert display.detail == "Rp 20"
    assert display.status == "completed"


def test_merge_corp_action_events_dedupes_and_keeps_history_newest_first():
    ticker_cache = [
        CorporateActionEvent(
            ticker="BBCA",
            event_type="__NONE__",
        ),
        CorporateActionEvent(
            ticker="BBCA",
            event_type="DIVIDEND",
            ex_date=date(2026, 6, 17),
            cum_date=date(2026, 6, 15),
            detail="Rp 20",
            status="completed",
        ),
    ]
    calendar = [
        CorporateActionEvent(
            ticker="BBCA",
            event_type="dividend",
            ex_date=date(2026, 6, 17),
            cum_date=date(2026, 6, 15),
            detail="Rp 20",
            status="completed",
        ),
        CorporateActionEvent(
            ticker="BBCA",
            event_type="dividend",
            ex_date=date(2026, 3, 30),
            cum_date=date(2026, 3, 27),
            detail="Rp 281",
            status="completed",
        ),
    ]

    merged = _merge_corp_action_events(ticker_cache, calendar)

    assert len(merged) == 2
    assert merged[0].ex_date == date(2026, 6, 17)
    assert merged[1].ex_date == date(2026, 3, 30)
