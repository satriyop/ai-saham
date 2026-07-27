"""
Stockbit corporate action event parsers — extracted parsing logic for
market-wide corporate action calendar endpoints.

Parses raw Stockbit Exodus API response bodies into normalized
CorporateActionCalendarEvent value objects.

Layer: Infrastructure
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from typing import Callable

from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────


def _fallback_id(event_type: str, ticker: str, dates: list[str], raw: dict) -> str:
    """Deterministic id when a source id field is missing/empty. Never uses hash()."""
    composite = (
        f"{event_type}|{ticker}|"
        f"{'|'.join(sorted(d for d in dates if d))}|"
        f"{json.dumps(raw, sort_keys=True, default=str)}"
    )
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()


def _parse_date(raw: object) -> date | None:
    """Parse a 'YYYY-MM-DD' string. None/''/unparseable -> None (no date row)."""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        logger.debug("Unparseable calendar date: %r", raw)
        return None


def _note(item: dict) -> str | None:
    note = item.get("event_note")
    return str(note) if note else None


def _build_event(
    *,
    event_type: CorporateActionType,
    item: dict,
    source_id_raw: object,
    date_specs: list[tuple[CorporateActionDateRole, object, str | None]],
    fetched_at: str,
    event_note: str | None,
    amount_value: str | None = None,
    amount_currency: str | None = None,
    ratio_old: str | None = None,
    ratio_new: str | None = None,
    price: str | None = None,
    company_name: str | None = None,
) -> CorporateActionCalendarEvent | None:
    ticker_raw = item.get("company_symbol")
    if not ticker_raw:
        return None
    ticker = str(ticker_raw).upper()

    dates: list[CorporateActionCalendarDate] = []
    parsed_date_strs: list[str] = []
    for role, raw_date, event_time in date_specs:
        parsed = _parse_date(raw_date)
        if parsed is None:
            continue
        dates.append(
            CorporateActionCalendarDate(
                date_role=role,
                event_date=parsed,
                event_time=event_time or None,
            )
        )
        parsed_date_strs.append(parsed.isoformat())

    source_id = str(source_id_raw).strip() if source_id_raw else ""
    if not source_id:
        source_id = _fallback_id(event_type.value, ticker, parsed_date_strs, item)

    return CorporateActionCalendarEvent(
        event_type=event_type,
        source_event_id=source_id,
        ticker=ticker,
        dates=tuple(dates),
        source="stockbit",
        company_id=(str(item["company_id"]) if item.get("company_id") is not None else None),
        company_name=company_name if company_name is not None else item.get("company_name"),
        active=bool(item.get("corp_action_active")),
        event_note=event_note,
        amount_value=amount_value,
        amount_currency=amount_currency,
        ratio_old=ratio_old,
        ratio_new=ratio_new,
        price=price,
        raw_payload_json=json.dumps(item, sort_keys=True, default=str),
        fetched_at=fetched_at,
    )


# ── Per-type row parsers ───────────────────────────────────────────────────


def _parse_dividend_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    return _build_event(
        event_type=CorporateActionType.DIVIDEND,
        item=item,
        source_id_raw=item.get("dividend_id"),
        date_specs=[
            (CorporateActionDateRole.CUM_DATE, item.get("dividend_cumdate"), None),
            (CorporateActionDateRole.EX_DATE, item.get("dividend_exdate"), None),
            (CorporateActionDateRole.RECORDING_DATE, item.get("dividend_recdate"), None),
            (CorporateActionDateRole.PAYMENT_DATE, item.get("dividend_paydate"), None),
        ],
        fetched_at=fetched_at,
        event_note=_note(item),
        amount_value=(str(item["dividend_value"]) if item.get("dividend_value") else None),
        amount_currency=item.get("dividend_currency") or None,
    )


def _parse_stocksplit_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    return _build_event(
        event_type=CorporateActionType.STOCK_SPLIT,
        item=item,
        source_id_raw=item.get("stocksplit_id"),
        date_specs=[
            (CorporateActionDateRole.CUM_DATE, item.get("stocksplit_cumdate"), None),
            (CorporateActionDateRole.EX_DATE, item.get("stocksplit_exdate"), None),
            (CorporateActionDateRole.RECORDING_DATE, item.get("stocksplit_recdate"), None),
        ],
        fetched_at=fetched_at,
        event_note=_note(item),
        ratio_old=(str(item["stocksplit_old"]) if item.get("stocksplit_old") else None),
        ratio_new=(str(item["stocksplit_new"]) if item.get("stocksplit_new") else None),
    )


def _parse_reversesplit_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    return _build_event(
        event_type=CorporateActionType.REVERSE_SPLIT,
        item=item,
        source_id_raw=item.get("stock_reverse_id"),
        date_specs=[
            (CorporateActionDateRole.CUM_DATE, item.get("stock_reverse_cumdate"), None),
            (CorporateActionDateRole.EX_DATE, item.get("stock_reverse_exdate"), None),
            (CorporateActionDateRole.RECORDING_DATE, item.get("stock_reverse_recdate"), None),
        ],
        fetched_at=fetched_at,
        event_note=_note(item),
        ratio_old=(str(item["stock_reverse_old"]) if item.get("stock_reverse_old") else None),
        ratio_new=(str(item["stock_reverse_new"]) if item.get("stock_reverse_new") else None),
    )


def _parse_rightissue_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    price = item.get("rightissue_price")
    return _build_event(
        event_type=CorporateActionType.RIGHTS_ISSUE,
        item=item,
        source_id_raw=item.get("rightissue_id"),
        date_specs=[
            (CorporateActionDateRole.CUM_DATE, item.get("rightissue_cumdate"), None),
            (CorporateActionDateRole.EX_DATE, item.get("rightissue_exdate"), None),
            (CorporateActionDateRole.RECORDING_DATE, item.get("rightissue_recdate"), None),
            (CorporateActionDateRole.SUBSCRIPTION_DATE, item.get("rightissue_subdate"), None),
            (CorporateActionDateRole.TRADING_START, item.get("rightissue_trading_start"), None),
            (CorporateActionDateRole.TRADING_END, item.get("rightissue_trading_end"), None),
        ],
        fetched_at=fetched_at,
        event_note=_note(item),
        ratio_old=(str(item["rightissue_old"]) if item.get("rightissue_old") else None),
        ratio_new=(str(item["rightissue_new"]) if item.get("rightissue_new") else None),
        price=(str(price) if price not in (None, "") else None),
    )


def _parse_bonus_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    return _build_event(
        event_type=CorporateActionType.BONUS,
        item=item,
        source_id_raw=item.get("sahabonus_id"),
        date_specs=[
            (CorporateActionDateRole.CUM_DATE, item.get("stocksplit_cumdate"), None),
            (CorporateActionDateRole.EX_DATE, item.get("stocksplit_exdate"), None),
            (CorporateActionDateRole.RECORDING_DATE, item.get("stocksplit_recdate"), None),
            (CorporateActionDateRole.PAYMENT_DATE, item.get("stocksplit_paymentdate"), None),
        ],
        fetched_at=fetched_at,
        event_note=_note(item),
        ratio_old=(str(item["stocksplit_old"]) if item.get("stocksplit_old") else None),
        ratio_new=(str(item["stocksplit_new"]) if item.get("stocksplit_new") else None),
    )


def _parse_tenderoffer_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    price = item.get("tender_price")
    return _build_event(
        event_type=CorporateActionType.TENDER_OFFER,
        item=item,
        source_id_raw=item.get("tender_id"),
        date_specs=[
            (CorporateActionDateRole.OFFER_START, item.get("tender_start"), None),
            (CorporateActionDateRole.OFFER_END, item.get("tender_end"), None),
            (CorporateActionDateRole.PAYMENT_DATE, item.get("tender_paydate"), None),
        ],
        fetched_at=fetched_at,
        event_note=_note(item),
        price=(str(price) if price not in (None, "") else None),
        company_name=item.get("company_name"),
    )


def _parse_rups_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    rups_time = item.get("rups_time")
    return _build_event(
        event_type=CorporateActionType.RUPS,
        item=item,
        source_id_raw=item.get("rups_id"),
        date_specs=[
            (
                CorporateActionDateRole.RUPS_DATE,
                item.get("rups_date"),
                str(rups_time) if rups_time else None,
            ),
            (CorporateActionDateRole.ELIGIBLE_DATE, item.get("rups_eligible_date"), None),
        ],
        fetched_at=fetched_at,
        event_note=None,
        company_name=item.get("company_name"),
    )


def _parse_pubex_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    puexp_time = item.get("puexp_time")
    return _build_event(
        event_type=CorporateActionType.PUBEX,
        item=item,
        source_id_raw=item.get("puexp_id"),
        date_specs=[
            (
                CorporateActionDateRole.PUBEX_DATE,
                item.get("puexp_date"),
                str(puexp_time) if puexp_time else None,
            ),
        ],
        fetched_at=fetched_at,
        event_note=None,
    )


def _parse_ipo_row(item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
    detail = item.get("ipo_data_detail")
    detail = detail if isinstance(detail, dict) else {}

    price: str | None = None
    ipo_price = item.get("ipo_price")
    if isinstance(ipo_price, dict) and ipo_price.get("final") is not None:
        price = str(ipo_price.get("final"))
    elif detail.get("price") is not None:
        price = str(detail.get("price"))

    return _build_event(
        event_type=CorporateActionType.IPO,
        item=item,
        source_id_raw=item.get("ipo_id"),
        date_specs=[
            (CorporateActionDateRole.LISTING_DATE, item.get("ipo_listing_date"), None),
            (CorporateActionDateRole.OFFERING_START, detail.get("offering_start"), None),
            (CorporateActionDateRole.OFFERING_END, detail.get("offering_end"), None),
            (CorporateActionDateRole.ALLOTMENT_DATE, detail.get("allotment_date"), None),
            (CorporateActionDateRole.REFUND_DATE, detail.get("refund_date"), None),
        ],
        fetched_at=fetched_at,
        event_note=_note(item),
        price=price,
        company_name=item.get("company_name"),
    )


# ── Event-type mapping ─────────────────────────────────────────────────────


_EVENT_TYPE_MAP: dict[CorporateActionType, tuple[str, Callable]] = {
    CorporateActionType.DIVIDEND: ("dividend", _parse_dividend_row),
    CorporateActionType.STOCK_SPLIT: ("stocksplit", _parse_stocksplit_row),
    CorporateActionType.REVERSE_SPLIT: ("stock_reverse", _parse_reversesplit_row),
    CorporateActionType.RIGHTS_ISSUE: ("rightissue", _parse_rightissue_row),
    CorporateActionType.BONUS: ("bonus", _parse_bonus_row),
    CorporateActionType.TENDER_OFFER: ("tender", _parse_tenderoffer_row),
    CorporateActionType.RUPS: ("rups", _parse_rups_row),
    CorporateActionType.PUBEX: ("pubex", _parse_pubex_row),
    CorporateActionType.IPO: ("ipo", _parse_ipo_row),
}


# ── Public API ─────────────────────────────────────────────────────────────


def parse_corporate_action_items(
    event_type: CorporateActionType,
    body: dict,
    *,
    fetched_at: str,
) -> list[CorporateActionCalendarEvent]:
    """Parse a raw corporate action API response into a list of events.

    Handles body-shape guards, list-key lookup, per-row iteration, and
    per-row exception guards. Returns [] for empty/malformed payloads.
    """
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return []

    list_key, parser = _EVENT_TYPE_MAP[event_type]

    items = data.get(list_key)
    if not isinstance(items, list):
        return []

    events: list[CorporateActionCalendarEvent] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            event = parser(item, fetched_at)
            if event is not None:
                events.append(event)
        except Exception as e:
            logger.warning("Skipping malformed %s row: %s", event_type.value, e)
    return events
