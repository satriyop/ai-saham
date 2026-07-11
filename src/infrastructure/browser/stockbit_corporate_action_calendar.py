"""
StockbitCorporateActionCalendarProvider — market-wide corporate action calendar.

Fetches the 9 market-wide Stockbit Exodus corpaction endpoints (dividend,
stocksplit, reversesplit, rightissue, bonus, tenderoffer, rups, pubex, ipo) and
parses each into normalized CorporateActionCalendarEvent value objects.

This provider is fetch + parse ONLY — no caching, no db_path, no persistence.
Persistence is entirely the repository's job. It deliberately does NOT subclass
StockbitCachingProvider (which the per-ticker provider uses); that separation
keeps the market-wide pipeline's fetch and store concerns cleanly split.

Reuses api_client.get(url) -> dict | None, which returns None on any HTTP/auth
failure (per the StockbitApiClient contract).

Layer: Infrastructure
Depends on: StockbitApiClient, StockbitConfig, corporate_action_calendar value objects
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from src.application.ports.corporate_action_calendar_provider import (
    CorporateActionCalendarFetchError,
    CorporateActionCalendarProvider,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)


def _fallback_id(event_type: str, ticker: str, dates: list[str], raw: dict) -> str:
    """Deterministic id when a source id field is missing/empty. Never uses hash()."""
    composite = (
        f"{event_type}|{ticker}|"
        f"{'|'.join(sorted(d for d in dates if d))}|"
        f"{json.dumps(raw, sort_keys=True, default=str)}"
    )
    return hashlib.sha256(composite.encode("utf-8")).hexdigest()


def _parse_date(raw: object) -> date | None:
    """Parse a 'YYYY-MM-DD' string. None/''/unparseable → None (no date row)."""
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


class StockbitCorporateActionCalendarProvider(CorporateActionCalendarProvider):
    """Fetches market-wide corporate action calendar events from Stockbit Exodus."""

    def __init__(self, api_client: "StockbitApiClient") -> None:
        self._api_client = api_client

    # ── Port implementation ────────────────────────────────────────────────

    def fetch_events(
        self, event_types: tuple[CorporateActionType, ...]
    ) -> list[CorporateActionCalendarEvent]:
        all_events: list[CorporateActionCalendarEvent] = []
        reason_by_type: dict[CorporateActionType, str] = {}

        for event_type in event_types:
            url = self._url_for(event_type)
            if url is None:
                reason_by_type[event_type] = "unsupported"
                continue

            body = self._api_client.get(url)
            if not body:
                # None/empty per StockbitApiClient contract = auth or network failure.
                reason_by_type[event_type] = "auth-or-network"
                continue

            try:
                parsed = self._parse_body(event_type, body)
                all_events.extend(parsed)
            except Exception as e:  # whole-endpoint parse guard
                logger.warning("Calendar parse failed for %s: %s", event_type.value, e)
                reason_by_type[event_type] = f"parse-error:{e}"

        if reason_by_type:
            raise CorporateActionCalendarFetchError(
                partial_events=all_events,
                failed_event_types=tuple(reason_by_type),
                reason_by_type=reason_by_type,
            )
        return all_events

    # ── URL mapping ────────────────────────────────────────────────────────

    def _url_for(self, event_type: CorporateActionType) -> str | None:
        return {
            CorporateActionType.DIVIDEND: STOCKBIT_CFG.calendar_dividend_url,
            CorporateActionType.STOCK_SPLIT: STOCKBIT_CFG.calendar_stocksplit_url,
            CorporateActionType.REVERSE_SPLIT: STOCKBIT_CFG.calendar_reversesplit_url,
            CorporateActionType.RIGHTS_ISSUE: STOCKBIT_CFG.calendar_rightissue_url,
            CorporateActionType.BONUS: STOCKBIT_CFG.calendar_bonus_url,
            CorporateActionType.TENDER_OFFER: STOCKBIT_CFG.calendar_tenderoffer_url,
            CorporateActionType.RUPS: STOCKBIT_CFG.calendar_rups_url,
            CorporateActionType.PUBEX: STOCKBIT_CFG.calendar_pubex_url,
            CorporateActionType.IPO: STOCKBIT_CFG.calendar_ipo_url,
        }.get(event_type)

    # ── Body dispatch ──────────────────────────────────────────────────────

    def _parse_body(
        self, event_type: CorporateActionType, body: dict
    ) -> list[CorporateActionCalendarEvent]:
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            return []

        list_key, parser = {
            CorporateActionType.DIVIDEND: ("dividend", self._parse_dividend),
            CorporateActionType.STOCK_SPLIT: ("stocksplit", self._parse_stocksplit),
            CorporateActionType.REVERSE_SPLIT: ("stock_reverse", self._parse_reversesplit),
            CorporateActionType.RIGHTS_ISSUE: ("rightissue", self._parse_rightissue),
            CorporateActionType.BONUS: ("bonus", self._parse_bonus),
            CorporateActionType.TENDER_OFFER: ("tender", self._parse_tenderoffer),
            CorporateActionType.RUPS: ("rups", self._parse_rups),
            CorporateActionType.PUBEX: ("pubex", self._parse_pubex),
            CorporateActionType.IPO: ("ipo", self._parse_ipo),
        }[event_type]

        items = data.get(list_key)
        if not isinstance(items, list):
            return []

        fetched_at = datetime.now().isoformat()
        events: list[CorporateActionCalendarEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                event = parser(item, fetched_at)
                if event is not None:
                    events.append(event)
            except Exception as e:  # per-row guard — never abort the endpoint
                logger.warning(
                    "Skipping malformed %s row: %s", event_type.value, e
                )
        return events

    # ── Shared builder ─────────────────────────────────────────────────────

    def _build_event(
        self,
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

    @staticmethod
    def _note(item: dict) -> str | None:
        note = item.get("event_note")
        return str(note) if note else None

    # ── Per-type parsers ───────────────────────────────────────────────────

    def _parse_dividend(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        return self._build_event(
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
            event_note=self._note(item),
            amount_value=(str(item["dividend_value"]) if item.get("dividend_value") else None),
            amount_currency=item.get("dividend_currency") or None,
        )

    def _parse_stocksplit(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        return self._build_event(
            event_type=CorporateActionType.STOCK_SPLIT,
            item=item,
            source_id_raw=item.get("stocksplit_id"),
            date_specs=[
                (CorporateActionDateRole.CUM_DATE, item.get("stocksplit_cumdate"), None),
                (CorporateActionDateRole.EX_DATE, item.get("stocksplit_exdate"), None),
                (CorporateActionDateRole.RECORDING_DATE, item.get("stocksplit_recdate"), None),
            ],
            fetched_at=fetched_at,
            event_note=self._note(item),
            ratio_old=(str(item["stocksplit_old"]) if item.get("stocksplit_old") else None),
            ratio_new=(str(item["stocksplit_new"]) if item.get("stocksplit_new") else None),
        )

    def _parse_reversesplit(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        return self._build_event(
            event_type=CorporateActionType.REVERSE_SPLIT,
            item=item,
            source_id_raw=item.get("stock_reverse_id"),
            date_specs=[
                (CorporateActionDateRole.CUM_DATE, item.get("stock_reverse_cumdate"), None),
                (CorporateActionDateRole.EX_DATE, item.get("stock_reverse_exdate"), None),
                (CorporateActionDateRole.RECORDING_DATE, item.get("stock_reverse_recdate"), None),
            ],
            fetched_at=fetched_at,
            event_note=self._note(item),
            ratio_old=(str(item["stock_reverse_old"]) if item.get("stock_reverse_old") else None),
            ratio_new=(str(item["stock_reverse_new"]) if item.get("stock_reverse_new") else None),
        )

    def _parse_rightissue(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        price = item.get("rightissue_price")
        return self._build_event(
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
            event_note=self._note(item),
            ratio_old=(str(item["rightissue_old"]) if item.get("rightissue_old") else None),
            ratio_new=(str(item["rightissue_new"]) if item.get("rightissue_new") else None),
            price=(str(price) if price not in (None, "") else None),
        )

    def _parse_bonus(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        # Bonus reuses stocksplit_* field names per documented Stockbit behavior.
        return self._build_event(
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
            event_note=self._note(item),
            ratio_old=(str(item["stocksplit_old"]) if item.get("stocksplit_old") else None),
            ratio_new=(str(item["stocksplit_new"]) if item.get("stocksplit_new") else None),
        )

    def _parse_tenderoffer(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        price = item.get("tender_price")
        return self._build_event(
            event_type=CorporateActionType.TENDER_OFFER,
            item=item,
            source_id_raw=item.get("tender_id"),
            date_specs=[
                (CorporateActionDateRole.OFFER_START, item.get("tender_start"), None),
                (CorporateActionDateRole.OFFER_END, item.get("tender_end"), None),
                (CorporateActionDateRole.PAYMENT_DATE, item.get("tender_paydate"), None),
            ],
            fetched_at=fetched_at,
            event_note=self._note(item),
            price=(str(price) if price not in (None, "") else None),
            company_name=item.get("company_name"),
        )

    def _parse_rups(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        rups_time = item.get("rups_time")
        return self._build_event(
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
            event_note=None,  # venue is not stored as event_note per schema
            company_name=item.get("company_name"),
        )

    def _parse_pubex(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        puexp_time = item.get("puexp_time")
        return self._build_event(
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

    def _parse_ipo(self, item: dict, fetched_at: str) -> CorporateActionCalendarEvent | None:
        detail = item.get("ipo_data_detail")
        detail = detail if isinstance(detail, dict) else {}

        price: str | None = None
        ipo_price = item.get("ipo_price")
        if isinstance(ipo_price, dict) and ipo_price.get("final") is not None:
            price = str(ipo_price.get("final"))
        elif detail.get("price") is not None:
            price = str(detail.get("price"))

        return self._build_event(
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
            event_note=self._note(item),
            price=price,
            company_name=item.get("company_name"),
        )
