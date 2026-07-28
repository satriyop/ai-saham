"""
StockbitMacroCalendarProvider — market-wide macroeconomic calendar.

Fetches GET /corpaction/economic and parses into MacroCalendarEvent VOs.
Fetch + parse ONLY — no caching, no persistence.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from src.application.ports.macro_calendar_provider import (
    MacroCalendarFetchError,
    MacroCalendarProvider,
)
from src.domain.value_objects.macro_calendar_event import MacroCalendarEvent
from src.infrastructure.browser.stockbit_macro_calendar_parsers import parse_economic_body
from src.infrastructure.config.macro_calendar_config import (
    MacroCalendarConfig,
    load_macro_calendar_config,
)
from src.infrastructure.config.stockbit_config import StockbitConfig, load_stockbit_config

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient

logger = logging.getLogger(__name__)


class StockbitMacroCalendarProvider(MacroCalendarProvider):
    """Fetches macroeconomic calendar events from Stockbit Exodus economic endpoint."""

    def __init__(
        self,
        api_client: "StockbitApiClient",
        stockbit_config: StockbitConfig | None = None,
        category_config: MacroCalendarConfig | None = None,
    ) -> None:
        self._api_client = api_client
        self._stockbit_config = stockbit_config or load_stockbit_config()
        self._category_config = (
            category_config if category_config is not None else load_macro_calendar_config()
        )

    def fetch_events(self) -> list[MacroCalendarEvent]:
        url = self._stockbit_config.calendar_economic_url
        body = self._api_client.get(url)
        if not body:
            raise MacroCalendarFetchError(
                reason="auth-or-network",
                partial_events=[],
            )

        try:
            return parse_economic_body(
                body,
                fetched_at=datetime.now().isoformat(),
                category_config=self._category_config,
            )
        except Exception as e:
            logger.warning("Macro calendar parse failed: %s", e)
            raise MacroCalendarFetchError(
                reason=f"parse-error:{e}",
                partial_events=[],
            ) from e
