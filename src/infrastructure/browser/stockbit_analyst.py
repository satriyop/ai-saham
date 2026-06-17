"""
StockbitAnalystConsensusProvider — analyst buy/hold/sell ratings from Stockbit.

Calls /analyst-ratings/{ticker} and returns an AnalystConsensus object.

Actual API shape (confirmed 2026-06):
  data.recommendation   → "Buy" | "Hold" | "Sell"
  data.total_buy        → int
  data.total_hold       → int
  data.total_sell       → int
  data.total_analyst    → int
  data.price_target.best_target    → int (IDR)
  data.price_target.current_price  → int (IDR)
  data.last_updated     → "15 Jun 26" (DD Mon YY)

Caching: in-memory per ticker — data changes at most daily; static within session.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from src.domain.ports.analyst_consensus_provider import AnalystConsensusProvider
from src.domain.value_objects.analyst_consensus import AnalystConsensus

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

logger = logging.getLogger(__name__)

_ANALYST_URL = "https://exodus.stockbit.com/analyst-ratings/{ticker}"


def _parse_date(raw: str) -> date | None:
    if not raw:
        return None
    for fmt in ("%d %b %y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_consensus(ticker: str, body: dict) -> AnalystConsensus | None:
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None

    buy = int(data.get("total_buy") or 0)
    hold = int(data.get("total_hold") or 0)
    sell = int(data.get("total_sell") or 0)

    pt = data.get("price_target") or {}
    avg_target = float(pt.get("best_target") or 0) or None
    current = float(pt.get("current_price") or 0) or None

    last_updated = _parse_date(str(data.get("last_updated") or ""))

    if buy + hold + sell == 0:
        return None

    return AnalystConsensus(
        ticker=ticker.upper(),
        buy_count=buy,
        hold_count=hold,
        sell_count=sell,
        avg_price_target=avg_target,
        current_price=current,
        last_updated=last_updated,
    )


class StockbitAnalystConsensusProvider(AnalystConsensusProvider):
    """Fetches analyst consensus from Stockbit Exodus API.

    In-memory cache keyed by ticker — analyst data changes at most daily;
    static within a CLI session.
    """

    def __init__(self, broker_provider: "StockbitPlaywrightBrokerProvider") -> None:
        self._provider = broker_provider
        self._cache: dict[str, AnalystConsensus | None] = {}

    def get_consensus(self, ticker: str) -> AnalystConsensus | None:
        key = ticker.upper()
        if key in self._cache:
            return self._cache[key]
        result = self._fetch(ticker)
        self._cache[key] = result
        return result

    def _fetch(self, ticker: str) -> AnalystConsensus | None:
        try:
            from src.infrastructure.browser.playwright_stockbit import _exodus_get
            token = self._provider._get_token()
            url = _ANALYST_URL.format(ticker=ticker.upper())
            body = _exodus_get(url, token)
            if not body:
                logger.debug("Empty analyst response for %s", ticker)
                return None
            result = _parse_consensus(ticker, body)
            if result:
                logger.debug("Analyst %s → %s (%d analysts)", ticker, result.consensus_label, result.analyst_count)
            return result
        except Exception as e:
            logger.warning("Analyst fetch failed for %s: %s", ticker, e)
            return None
