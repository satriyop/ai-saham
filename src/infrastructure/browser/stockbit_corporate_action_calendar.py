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

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from src.application.ports.corporate_action_calendar_provider import (
    CorporateActionCalendarFetchError,
    CorporateActionCalendarProvider,
)
from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarEvent,
    CorporateActionType,
)
from src.infrastructure.browser.stockbit_corporate_action_event_parsers import (
    parse_corporate_action_items,
)
from src.infrastructure.config.stockbit_config import StockbitConfig, load_stockbit_config

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)


class StockbitCorporateActionCalendarProvider(CorporateActionCalendarProvider):
    """Fetches market-wide corporate action calendar events from Stockbit Exodus."""

    def __init__(
        self, api_client: "StockbitApiClient", stockbit_config: StockbitConfig | None = None
    ) -> None:
        self._api_client = api_client
        self._stockbit_config = stockbit_config or load_stockbit_config()

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
            CorporateActionType.DIVIDEND: self._stockbit_config.calendar_dividend_url,
            CorporateActionType.STOCK_SPLIT: self._stockbit_config.calendar_stocksplit_url,
            CorporateActionType.REVERSE_SPLIT: self._stockbit_config.calendar_reversesplit_url,
            CorporateActionType.RIGHTS_ISSUE: self._stockbit_config.calendar_rightissue_url,
            CorporateActionType.BONUS: self._stockbit_config.calendar_bonus_url,
            CorporateActionType.TENDER_OFFER: self._stockbit_config.calendar_tenderoffer_url,
            CorporateActionType.RUPS: self._stockbit_config.calendar_rups_url,
            CorporateActionType.PUBEX: self._stockbit_config.calendar_pubex_url,
            CorporateActionType.IPO: self._stockbit_config.calendar_ipo_url,
        }.get(event_type)

    # ── Body dispatch ──────────────────────────────────────────────────────

    def _parse_body(
        self, event_type: CorporateActionType, body: dict
    ) -> list[CorporateActionCalendarEvent]:
        return parse_corporate_action_items(
            event_type, body, fetched_at=datetime.now().isoformat()
        )
