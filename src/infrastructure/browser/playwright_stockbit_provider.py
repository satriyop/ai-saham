"""
Stockbit pre-open/IEV provider module.

Contains PlaywrightStockbitProvider — IEV/OrderBook provider backed by
StockbitApiClient.

StockbitBrokerProvider now lives in stockbit_broker_provider.py.
Broker/foreign-flow JSON parsing lives in stockbit_broker_parsers.py.
IEV/orderbook JSON parsing lives in stockbit_preopen_parsers.py.

Browser session utilities (login, spy, browse, JWT extraction) live in
stockbit_session_actions.py / stockbit_token_extractor.py (with a compatibility
facade in playwright_stockbit_browser.py) and are re-exported from here.

Phase D+E: browser launches removed from data-fetching methods. All Exodus API
calls now go through StockbitApiClient (JWT managed by StockbitTokenStore).

Flow:
  saham fetch stockbit login   → saves persistent browser profile + JWT
  saham fetch stockbit spy     → captures all API traffic to identify endpoints
  saham screen pre-open        → uses saved session for autonomous screening

Layer: Infrastructure
Depends on: StockbitApiClient, BrowserDataProvider port
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.value_objects.screener_result import (
    MoverData,
    MoverWithOrderBook,
    OrderBookBid,
    OrderBookTopOfBook,
)
from src.infrastructure.browser.stockbit_api_client import StockbitApiClient
from src.infrastructure.browser.stockbit_browser_context import (
    NAV_TIMEOUT as NAV_TIMEOUT,
)
from src.infrastructure.browser.stockbit_browser_context import (
    ORDERBOOK_PAGE_URL as ORDERBOOK_PAGE_URL,
)
from src.infrastructure.browser.stockbit_browser_context import (
    SPA_SETTLE_MS as SPA_SETTLE_MS,
)
from src.infrastructure.browser.stockbit_browser_context import (
    _persistent_context as _persistent_context,
)
from src.infrastructure.browser.stockbit_browser_context import (
    _require_playwright as _require_playwright,
)
from src.infrastructure.browser.stockbit_preopen_parsers import (
    _parse_iev_response,
    _parse_top_of_book,
)
from src.infrastructure.browser.stockbit_session_actions import (
    browse_stockbit_session as browse_stockbit_session,
)
from src.infrastructure.browser.stockbit_session_actions import (
    get_stockbit_session_status as get_stockbit_session_status,
)
from src.infrastructure.browser.stockbit_session_actions import (
    save_stockbit_session as save_stockbit_session,
)
from src.infrastructure.browser.stockbit_token_extractor import (
    _intercept_token as _intercept_token,
)
from src.infrastructure.browser.stockbit_token_extractor import (
    _resolve_token as _resolve_token,
)
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

logger = logging.getLogger(__name__)

# ── Session utilities — live in playwright_stockbit_browser, imported here ──
# Imports above remain explicit aliases for backward-compatible re-export.

_sb = STOCKBIT_CFG

_IEV_MOVER_URL_MAIN = _sb.iev_movers_main_url
_IEV_MOVER_URL_SPECIAL = _sb.iev_movers_special_url
_ORDER_BOOK_API = _sb.orderbook_url

ELEMENT_TIMEOUT = STOCKBIT_CFG.element_timeout_ms


# ── Main provider ──────────────────────────────────────────────────────────


class PlaywrightStockbitProvider(BrowserDataProvider):
    """
    Autonomous Stockbit IEV/OrderBook provider backed by StockbitApiClient.

    No browser launches for data — uses the persisted JWT via api_client.
    Authentication health (token validity, refresh) is entirely owned by
    StockbitApiClient/StockbitTokenStore; this provider never gates a
    request on browser-profile age.

    Usage:
        from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
        api_client = create_stockbit_api_client()
        provider = PlaywrightStockbitProvider(api_client=api_client)
        movers = provider.fetch_preopen_movers(iev_min=100_000)
        ob = provider.fetch_order_book_best_bid("BBCA")
    """

    def __init__(self, api_client: StockbitApiClient) -> None:
        self._api_client = api_client

    def fetch_preopen_movers(self, iev_min: int) -> list[MoverData]:
        """
        Fetch IEV movers from the Exodus API via StockbitApiClient.

        Flow:
          1. Call IEV movers API for main boards + special monitoring, merge results
          2. Parse and return MoverData list filtered by iev_min
        """
        try:
            all_movers = _fetch_iev_all_boards(self._api_client)
        except Exception as e:
            raise RuntimeError(f"IEV fetch failed: {e}\nRun: saham fetch stockbit login") from None
        return [m for m in all_movers if m.iev >= iev_min]

    def fetch_top5_iev_with_orderbooks(self, top_n: int = 5) -> list[MoverWithOrderBook]:
        """
        Fetch top-N IEV movers and their live orderbook snapshots.

        Flow:
          1. Call IEV movers API for all boards (main + special monitoring), merge
          2. Take top_n by IEV descending
          3. For each ticker, call orderbook API
          4. Return combined list

        Args:
            top_n: How many top IEV movers to return (default 5)

        Returns:
            List of MoverWithOrderBook sorted by IEV descending
        """
        all_movers = _fetch_iev_all_boards(self._api_client)
        top_movers = all_movers[:top_n]
        logger.info("Top %d movers: %s", len(top_movers), [m.ticker for m in top_movers])

        results: list[MoverWithOrderBook] = []
        for mover in top_movers:
            ob_url = _ORDER_BOOK_API.format(ticker=mover.ticker.upper())
            body = self._api_client.get(ob_url)
            bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
            results.append(
                MoverWithOrderBook(
                    ticker=mover.ticker,
                    iev=mover.iev,
                    best_bid=bid_price,
                    best_bid_lots=bid_lots,
                    best_offer=offer_price,
                    best_offer_lots=offer_lots,
                    iep=mover.iep,
                )
            )
            logger.info(
                "%s: bid=%s (%s lots)  offer=%s (%s lots)",
                mover.ticker,
                bid_price,
                bid_lots,
                offer_price,
                offer_lots,
            )

        return results

    def fetch_iev_snapshot(self, top_n: int = 50) -> list[MoverData]:
        """
        Fetch IEV movers for storage — no orderbook, IEV ranks only.

        Designed to be called at ~08:50 WIB to capture the pre-open mover list
        for historical backtesting. Returns up to top_n movers sorted by IEV desc.

        Args:
            top_n: Maximum movers to return (default 50 to capture a broad universe).
        """
        return _fetch_iev_all_boards(self._api_client)[:top_n]

    def _fetch_order_book_raw(self, ticker: str) -> OrderBookTopOfBook | None:
        """Fetch orderbook via api_client and return both bid and offer."""
        ob_url = _ORDER_BOOK_API.format(ticker=ticker.upper())
        body = self._api_client.get(ob_url)
        if not body:
            return None

        bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
        if bid_price is None and offer_price is None:
            data_block = body.get("data") if isinstance(body, dict) else None
            iepiev = (data_block or {}).get("iepiev") or {}
            bbo = iepiev.get("best_bid_offer") or {}
            bid_list = (data_block or {}).get("bid") or []
            offer_list = (data_block or {}).get("offer") or []
            logger.warning(
                "Order book no bid/offer for %s — "
                "bbo=%s  bbo.bid.price=%s  bid_list_len=%d  "
                "offer_list_len=%d  iep=%s  lastprice=%s",
                ticker,
                "present" if bbo else "MISSING",
                (bbo.get("bid") or {}).get("price", {}).get("raw", "MISSING"),
                len(bid_list),
                len(offer_list),
                iepiev.get("iep", {}).get("raw", "N/A"),
                (data_block or {}).get("lastprice", "N/A"),
            )
            return None

        bid = OrderBookBid(price=bid_price, volume=bid_lots) if bid_price and bid_lots else None
        offer = (
            OrderBookBid(price=offer_price, volume=offer_lots)
            if offer_price and offer_lots
            else None
        )
        logger.info(
            "Order book %s: bid=%s (%s lots)  offer=%s (%s lots)",
            ticker,
            bid_price,
            bid_lots,
            offer_price,
            offer_lots,
        )
        return OrderBookTopOfBook(bid=bid, offer=offer)

    def fetch_order_book_best_bid(self, ticker: str) -> OrderBookBid | None:
        """Fetch order book best bid. Delegates to _fetch_order_book_raw()."""
        tob = self._fetch_order_book_raw(ticker)
        return tob.bid if tob else None

    def fetch_order_book_top_of_book(self, ticker: str) -> OrderBookTopOfBook | None:
        """Fetch order book best bid and best offer."""
        return self._fetch_order_book_raw(ticker)


# ── Board-aware IEV fetcher ────────────────────────────────────────────────


def _fetch_iev_all_boards(api_client: StockbitApiClient) -> list[MoverData]:
    """
    Call IEV movers API for both board groups, merge, deduplicate, sort by IEV desc.

    Mirrors how the Stockbit frontend works: two separate API calls (main boards
    and special monitoring board), then combined into one sorted list.
    """
    seen: dict[str, MoverData] = {}

    for url in (_IEV_MOVER_URL_MAIN, _IEV_MOVER_URL_SPECIAL):
        body = api_client.get(url)
        if not body:
            logger.debug("No response from %s", url)
            continue
        for mover in _parse_iev_response(body, iev_min=0):
            # Keep highest IEV if ticker appears in both boards
            existing = seen.get(mover.ticker)
            if existing is None or mover.iev > existing.iev:
                seen[mover.ticker] = mover

    return sorted(
        seen.values(),
        key=lambda m: m.iev,
        reverse=True,
    )


# ── API patterns file (populated by spy) ──────────────────────────────────


def _load_api_patterns(path: Path) -> dict:
    """Load custom API patterns discovered by spy-session."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)
