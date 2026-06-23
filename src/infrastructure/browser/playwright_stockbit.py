"""
Playwright-based Stockbit browser provider.

Contains the two provider classes and all response parsers.
Browser session utilities (login, spy, browse, JWT extraction) live in
playwright_stockbit_browser.py and are re-exported from here for backward compat.

Two modes for IEV/orderbook:
  1. API-intercept mode (preferred): hooks Playwright's network layer to
     capture JSON responses, bypassing fragile DOM selectors entirely.
  2. DOM-scrape mode (fallback): parses rendered HTML tables.

Flow:
  saham fetch stockbit login   → saves persistent browser profile
  saham fetch stockbit spy     → captures all API traffic to identify endpoints
  saham fetch stockbit test    → smoke-tests the adapter with live data
  saham screen pre-open → uses saved session for autonomous screening

Layer: Infrastructure
Depends on: playwright (optional), BrowserDataProvider port
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerFlowPoint,
    BrokerSummary,
    BrokerTransaction,
    BrokerType,
    ForeignFlowPoint,
    ForeignFlowSnapshot,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProvider,
)
from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.value_objects.screener_result import (
    MoverData,
    MoverWithOrderBook,
    OrderBookBid,
    OrderBookTopOfBook,
)

logger = logging.getLogger(__name__)

# ── Session utilities — live in playwright_stockbit_browser, imported here ──
from src.infrastructure.browser.playwright_stockbit_browser import (
    DEFAULT_PROFILE_DIR,
    NAV_TIMEOUT,
    ORDERBOOK_PAGE_URL,
    SPA_SETTLE_MS,
    StockbitSessionExpired,
    _exodus_get,
    _intercept_token,
    _persistent_context,
    _require_playwright,
    _resolve_token,
)

# ── Stockbit API config — driven by config/stockbit.yaml ─────────────────
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

_sb = STOCKBIT_CFG

_IEV_MOVER_URL_MAIN    = _sb.iev_movers_main_url
_IEV_MOVER_URL_SPECIAL = _sb.iev_movers_special_url
_ORDER_BOOK_API        = _sb.orderbook_url
_MARKETDETECTORS_API   = _sb.marketdetectors_url
_BROKER_ACTIVITY_API   = _sb.broker_activity_url
_BROKER_HISTORICAL_API  = _sb.broker_historical_url
_HISTORICAL_SUMMARY_API = _sb.historical_summary_url
_INSTITUTIONAL_PROXY_CODES = list(_sb.institutional_proxy_codes)
TRACKED_BROKER_CODES       = list(_sb.tracked_broker_codes)

ELEMENT_TIMEOUT = STOCKBIT_CFG.element_timeout_ms


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_number(text: str) -> int | None:
    """Parse a formatted number string like '1.234.567' or '1,234,567'."""
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None


# ── Main provider ──────────────────────────────────────────────────────────

class PlaywrightStockbitProvider(BrowserDataProvider):
    """
    Autonomous Stockbit provider using Playwright.

    Tries API-interception first (fast, reliable). Falls back to DOM scraping
    if no JSON responses match known patterns.

    Usage:
        provider = PlaywrightStockbitProvider(headless=True)
        movers = provider.fetch_preopen_movers(iev_min=100_000)
        ob = provider.fetch_order_book_best_bid("BBCA")
    """

    def __init__(
        self,
        profile_dir: Path = DEFAULT_PROFILE_DIR,
        headless: bool = True,
        timeout: int = NAV_TIMEOUT,
        api_patterns_file: Path | None = None,
    ) -> None:
        self._profile_dir = profile_dir
        self._headless = headless
        self._timeout = timeout
        self._api_patterns = _load_api_patterns(api_patterns_file) if api_patterns_file else {}

    def _assert_session_fresh(self) -> None:
        """Raise before launching a browser if the session marker is too old."""
        marker = self._profile_dir / ".logged_in_at"
        if not marker.exists():
            return  # no marker yet — first run after login
        try:
            age_hours = (time.time() - float(marker.read_text())) / 3600
        except Exception:
            return
        if age_hours >= 8:
            raise RuntimeError(
                f"Stockbit session is {age_hours:.1f}h old — likely expired.\n"
                "Run: saham fetch stockbit login"
            )

    def fetch_preopen_movers(self, iev_min: int) -> list[MoverData]:
        """
        Fetch IEV movers from the Exodus API using a JWT extracted from the browser.

        Flow:
          1. Open orderbook page (reliably fires Bearer-authenticated Exodus requests)
          2. Intercept RS256 Bearer token from request headers
          3. Call market-mover for main boards + special monitoring, merge results
          4. Parse and return MoverData list filtered by iev_min
        """
        self._assert_session_fresh()
        sync_playwright = _require_playwright()

        with sync_playwright() as pw:
            ctx, page = _persistent_context(pw, self._profile_dir, self._headless)

            try:
                token = _intercept_token(page)
                # ORDERBOOK_PAGE_URL reliably fires Bearer-authenticated Exodus requests.
                # STREAM_URL does not fire Bearer requests within the settle window.
                page.goto(ORDERBOOK_PAGE_URL, timeout=self._timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(SPA_SETTLE_MS)

                resolved = _resolve_token(page, token)
                if not resolved:
                    logger.warning("Could not extract JWT — falling back to DOM")
                    return _scrape_movers_from_dom(page, iev_min)

                logger.info("JWT extracted, calling Exodus IEV API (all boards)")
                try:
                    all_movers = _fetch_iev_all_boards(resolved)
                except StockbitSessionExpired as e:
                    raise RuntimeError(
                        f"{e}\n\nRun: saham fetch stockbit login"
                    ) from None

                filtered = [m for m in all_movers if m.iev >= iev_min]
                if filtered:
                    logger.info("Exodus API: %d movers (IEV >= %d)", len(filtered), iev_min)
                    return filtered
                logger.warning("Exodus API returned data but 0 movers matched IEV >= %d", iev_min)

                logger.info("Falling back to DOM scraping")
                return _scrape_movers_from_dom(page, iev_min)

            finally:
                ctx.close()

    def fetch_top5_iev_with_orderbooks(self, top_n: int = 5) -> list[MoverWithOrderBook]:
        """
        Fetch top-N IEV movers and their live orderbook snapshots in ONE browser session.
        Raises RuntimeError immediately if session marker is >= 8h old.

        Flow:
          1. Open browser, navigate to stream page to load auth state
          2. Extract JWT from localStorage
          3. Call IEV movers API for all boards (main + special monitoring), merge
          4. Take top_n by IEV descending
          5. For each ticker, call orderbook API via httpx
          6. Return combined list

        Args:
            top_n: How many top IEV movers to return (default 5)

        Returns:
            List of MoverWithOrderBook sorted by IEV descending
        """
        self._assert_session_fresh()
        sync_playwright = _require_playwright()

        with sync_playwright() as pw:
            ctx, page = _persistent_context(pw, self._profile_dir, self._headless)

            try:
                token_box = _intercept_token(page)
                page.goto(ORDERBOOK_PAGE_URL, timeout=self._timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(SPA_SETTLE_MS)

                token = _resolve_token(page, token_box)
                if not token:
                    logger.warning("Could not extract JWT for fetch_top5")
                    return []

                logger.info("Fetching IEV movers (all boards)...")
                try:
                    all_movers = _fetch_iev_all_boards(token)
                except StockbitSessionExpired as e:
                    raise RuntimeError(f"{e}\n\nRun: saham fetch stockbit login") from None
                top_movers = all_movers[:top_n]
                logger.info("Top %d movers: %s", len(top_movers), [m.ticker for m in top_movers])

                results: list[MoverWithOrderBook] = []
                for mover in top_movers:
                    ob_url = _ORDER_BOOK_API.format(ticker=mover.ticker.upper())
                    body = _exodus_get(ob_url, token)
                    bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
                    results.append(MoverWithOrderBook(
                        ticker=mover.ticker,
                        iev=mover.iev,
                        best_bid=bid_price,
                        best_bid_lots=bid_lots,
                        best_offer=offer_price,
                        best_offer_lots=offer_lots,
                        iep=mover.iep,
                    ))
                    logger.info(
                        "%s: bid=%s (%s lots)  offer=%s (%s lots)",
                        mover.ticker, bid_price, bid_lots, offer_price, offer_lots,
                    )

                return results

            finally:
                ctx.close()

    def fetch_iev_snapshot(self, top_n: int = 50) -> list[MoverData]:
        """
        Fetch IEV movers for storage — no orderbook, IEV ranks only.

        Designed to be called at ~08:50 WIB to capture the pre-open mover list
        for historical backtesting. Returns up to top_n movers sorted by IEV desc.

        Much faster than fetch_top5_iev_with_orderbooks (~15s vs ~45s) because
        it skips the per-ticker orderbook API calls.

        Args:
            top_n: Maximum movers to return (default 50 to capture a broad universe).
        """
        self._assert_session_fresh()
        sync_playwright = _require_playwright()

        with sync_playwright() as pw:
            ctx, page = _persistent_context(pw, self._profile_dir, self._headless)

            try:
                token_box = _intercept_token(page)
                page.goto(ORDERBOOK_PAGE_URL, timeout=self._timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(SPA_SETTLE_MS)

                token = _resolve_token(page, token_box)
                if not token:
                    logger.warning("Could not extract JWT for fetch_iev_snapshot")
                    return []

                logger.info("Fetching IEV movers for snapshot (top %d)...", top_n)
                try:
                    all_movers = _fetch_iev_all_boards(token)
                except StockbitSessionExpired as e:
                    raise RuntimeError(f"{e}\n\nRun: saham fetch stockbit login") from None

                return all_movers[:top_n]

            finally:
                ctx.close()

    def _fetch_order_book_raw(self, ticker: str) -> OrderBookTopOfBook | None:
        """Single browser session: fetch orderbook and return both bid and offer."""
        sync_playwright = _require_playwright()

        with sync_playwright() as pw:
            ctx, page = _persistent_context(pw, self._profile_dir, self._headless)

            try:
                token_box = _intercept_token(page)
                page.goto(ORDERBOOK_PAGE_URL, timeout=self._timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(SPA_SETTLE_MS)

                token = _resolve_token(page, token_box)
                if not token:
                    logger.warning("Could not extract JWT for order book")
                    return None

                ob_url = _ORDER_BOOK_API.format(ticker=ticker.upper())
                body = _exodus_get(ob_url, token)
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
                offer = OrderBookBid(price=offer_price, volume=offer_lots) if offer_price and offer_lots else None
                logger.info(
                    "Order book %s: bid=%s (%s lots)  offer=%s (%s lots)",
                    ticker, bid_price, bid_lots, offer_price, offer_lots,
                )
                return OrderBookTopOfBook(bid=bid, offer=offer)

            finally:
                ctx.close()

    def fetch_order_book_best_bid(self, ticker: str) -> OrderBookBid | None:
        """Fetch order book best bid. Delegates to _fetch_order_book_raw()."""
        tob = self._fetch_order_book_raw(ticker)
        return tob.bid if tob else None

    def fetch_order_book_top_of_book(self, ticker: str) -> OrderBookTopOfBook | None:
        """Fetch order book best bid and best offer in one browser session."""
        return self._fetch_order_book_raw(ticker)


# ── Playwright-backed BrokerDataProvider ──────────────────────────────────

class StockbitPlaywrightBrokerProvider(BrokerDataProvider):
    """
    Implements BrokerDataProvider using the Playwright persistent browser session.

    Reuses the existing .stockbit_profile/ persistent context to extract an
    RS256 Bearer token, then makes direct httpx calls to the Exodus API.
    No manual token management needed — the browser session auto-refreshes.

    Usage:
        provider = StockbitPlaywrightBrokerProvider()
        summaries = provider.fetch_broker_summaries("BBCA", date(2026,1,1), date.today())
    """

    # In-process token cache: avoids launching Chromium on every request
    # during batch updates. Reset when session is re-created.
    _TOKEN_TTL_SECONDS = 1800  # 30 minutes

    def __init__(
        self,
        profile_dir: Path = DEFAULT_PROFILE_DIR,
        headless: bool = True,
        timeout: int = NAV_TIMEOUT,
    ) -> None:
        self._profile_dir = profile_dir
        self._headless = headless
        self._timeout = timeout
        self._token_cache: str | None = None
        self._token_cached_at: float = 0

    @property
    def provider_name(self) -> str:
        return "stockbit"

    def is_authenticated(self) -> bool:
        """True if a persistent profile exists and its login marker is < 72h old."""
        marker = self._profile_dir / ".logged_in_at"
        if not (self._profile_dir.exists() and marker.exists()):
            return False
        try:
            age_hours = (time.time() - float(marker.read_text())) / 3600
            return age_hours < 72
        except Exception:
            return False

    def _get_token(self) -> str:
        """
        Return a valid RS256 Bearer token.

        Uses a 30-minute in-process cache so batch updates don't launch
        Chromium for every ticker. On cache miss, opens the browser, navigates
        to ORDERBOOK_PAGE_URL (which reliably fires Bearer-authenticated Exodus
        requests), intercepts the token, then immediately closes the browser.
        """
        now = time.time()
        if self._token_cache and (now - self._token_cached_at) < self._TOKEN_TTL_SECONDS:
            return self._token_cache

        if not (self._profile_dir.exists() and any(self._profile_dir.iterdir())):
            raise BrokerDataAuthError(
                "No Stockbit session found.\nRun: saham fetch stockbit login"
            )

        sync_playwright = _require_playwright()
        token: str | None = None
        with sync_playwright() as pw:
            ctx, page = _persistent_context(pw, self._profile_dir, self._headless)
            try:
                token_box = _intercept_token(page)
                page.goto(ORDERBOOK_PAGE_URL, timeout=self._timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(SPA_SETTLE_MS)
                token = _resolve_token(page, token_box)
            finally:
                ctx.close()

        if not token:
            raise BrokerDataAuthError(
                "Could not extract auth token — session may be expired.\n"
                "Run: saham fetch stockbit login"
            )

        self._token_cache = token
        self._token_cached_at = time.time()
        # Refresh the marker — successful token extraction proves the session is alive
        marker = self._profile_dir / ".logged_in_at"
        marker.write_text(str(time.time()))
        return token

    def fetch_broker_summary(
        self,
        ticker: str,
        target_date: date,
    ) -> BrokerSummary | None:
        summaries = self.fetch_broker_summaries(ticker, target_date, target_date)
        return summaries[0] if summaries else None

    def fetch_broker_summaries(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[BrokerSummary]:
        """
        Fetch named broker breakdown for a specific ticker via marketdetectors endpoint.

        Uses the stock-centric Exodus API (confirmed 2026-06-13) which returns
        which named brokers bought/sold the stock in the requested period.
        Maps the date range to the closest supported period parameter.
        """
        token = self._get_token()
        days = (end_date - start_date).days
        # All confirmed valid as of 2026-06-13
        if days <= 1:
            period = "BROKER_SUMMARY_PERIOD_LATEST"
        elif days <= 7:
            period = "BROKER_SUMMARY_PERIOD_LAST_7_DAYS"
        elif days <= 30:
            period = "BROKER_SUMMARY_PERIOD_LAST_1_MONTH"
        elif days <= 90:
            period = "BROKER_SUMMARY_PERIOD_LAST_3_MONTHS"
        elif days <= 180:
            period = "BROKER_SUMMARY_PERIOD_LAST_6_MONTHS"
        else:
            period = "BROKER_SUMMARY_PERIOD_LAST_1_YEAR"
        url = (
            f"{_MARKETDETECTORS_API}/{ticker.upper()}"
            f"?transaction_type=TRANSACTION_TYPE_NET"
            f"&market_board=MARKET_BOARD_REGULER"
            f"&investor_type=INVESTOR_TYPE_ALL"
            f"&limit=25"
            f"&period={period}"
        )
        body = _exodus_get(url, token)
        if not body:
            logger.warning(
                "No broker data for %s (%s–%s). "
                "Run: saham fetch stockbit spy --target stock --ticker %s",
                ticker, start_date, end_date, ticker,
            )
            return []

        real_total = _fetch_historical_summary_totals(ticker, start_date, end_date, token)
        if real_total is None:
            logger.warning(
                "fetch_broker_summaries/%s: historical/summary unavailable, "
                "total_value will be synthetic (top-broker subset only)",
                ticker,
            )
        summaries = _parse_marketdetectors_response(ticker, end_date, body, real_total=real_total)
        if summaries:
            logger.info("Stockbit named broker data: %s → %d entry", ticker, len(summaries))
        else:
            logger.debug(
                "marketdetectors/%s returned data but no parseable broker rows. "
                "Run spy to inspect the response shape.",
                ticker,
            )
        return summaries

    def fetch_foreign_top_stocks(
        self,
        start_date: date,
        end_date: date,
        limit: int = 20,
    ) -> list[ForeignFlowSnapshot]:
        """
        Return stocks most actively traded by foreign brokers in the period.

        Uses the broker-centric Exodus API: given the 10 known foreign broker codes,
        returns which stocks they collectively bought/sold the most. Useful for
        universe-level screening ("is this IEV mover in foreign top buys?").
        """
        token = self._get_token()
        days = (end_date - start_date).days
        # Confirmed valid periods (2026-06-13): 1D, 3D, 7D, 1M, 3M, 1Y
        # LAST_1_WEEK and LAST_6_MONTHS are not valid values
        if days <= 1:
            period = "RT_PERIOD_LAST_1_DAY"
        elif days <= 3:
            period = "RT_PERIOD_LAST_3_DAYS"
        elif days <= 7:
            period = "RT_PERIOD_LAST_7_DAYS"
        elif days <= 30:
            period = "RT_PERIOD_LAST_1_MONTH"
        elif days <= 90:
            period = "RT_PERIOD_LAST_3_MONTHS"
        else:
            period = "RT_PERIOD_LAST_1_YEAR"
        broker_params = "&".join(f"broker_code={c}" for c in _INSTITUTIONAL_PROXY_CODES)
        url = (
            f"{_BROKER_ACTIVITY_API}?{broker_params}"
            f"&transaction_type=TRANSACTION_TYPE_NET"
            f"&investor_type=INVESTOR_TYPE_ALL"
            f"&limit={limit}&market_board=MARKET_TYPE_REGULER&page=1"
            f"&period={period}"
            f"&net_val_period=NET_VAL_PERIOD_7D"
        )
        body = _exodus_get(url, token)
        if not body:
            logger.warning("No response from broker-centric scan endpoint")
            return []
        snapshots = _parse_foreign_top_stocks(end_date, body)
        logger.info("Foreign top stocks scan: %d stocks returned", len(snapshots))
        return snapshots

    def fetch_foreign_flow_history(
        self,
        ticker: str,
        days: int = 365,
    ) -> list[ForeignFlowPoint]:
        """
        Return daily foreign broker flow for a stock, up to `days` back.

        Uses the stock-centric historical Exodus API. Returns daily N.Val/N.Lot
        time-series for trend context and backfilling the foreign-flow table.
        """
        token = self._get_token()
        codes_params = "&".join(f"broker_codes={c}" for c in _INSTITUTIONAL_PROXY_CODES)
        url = (
            f"{_BROKER_HISTORICAL_API}?interval=INTERVAL_DAILY"
            f"&period=RT_PERIOD_LAST_1_YEAR"
            f"&{codes_params}"
            f"&symbols={ticker.upper()}"
            f"&market_board=BOARD_TYPE_REGULAR"
            f"&investor_type=INVESTOR_TYPE_ALL"
            f"&pagination.page=1&pagination.limit={min(days, 365)}"
        )
        body = _exodus_get(url, token)
        if not body:
            logger.debug("No response from foreign flow history endpoint for %s", ticker)
            return []
        points = _parse_foreign_flow_history(ticker, body)
        logger.info("Foreign flow history: %s → %d data points", ticker, len(points))
        return points

    def fetch_foreign_flow_from_summary(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[ForeignFlowPoint]:
        """
        Fetch per-day foreign flow from the historical summary endpoint.

        One API call vs. many calls on the broker/activity/historical path.
        Use for bulk date-range backfills; reserve broker/activity/historical for
        per-broker detail or when you need net_lot accuracy.
        """
        all_points: list[ForeignFlowPoint] = []
        page = 1
        try:
            token = self._get_token()
            while True:
                url = (
                    f"{_HISTORICAL_SUMMARY_API.format(ticker=ticker.upper())}"
                    f"?period=HS_PERIOD_DAILY"
                    f"&start_date={start_date.isoformat()}"
                    f"&end_date={end_date.isoformat()}"
                    f"&limit=50&page={page}"
                )
                body = _exodus_get(url, token)
                if not body:
                    break
                rows = (body.get("data") or {}).get("result") or []
                if not rows:
                    break

                points = _parse_historical_summary_flow(ticker, body)
                all_points.extend(points)

                if len(rows) < 50:
                    break
                page += 1

            return sorted(all_points, key=lambda p: p.date)
        except Exception as e:
            logger.warning("fetch_foreign_flow_from_summary %s failed: %s", ticker, e)
            return []


    def fetch_broker_flow_history(
        self,
        ticker: str,
        days: int = 365,
    ) -> list[BrokerFlowPoint]:
        """Deprecated alias for fetch_foreign_flow_history."""
        return self.fetch_foreign_flow_history(ticker, days)

    def fetch_broker_daily_flows(
        self,
        ticker: str,
        broker_codes: list[str] | None = None,
        days: int = 365,
    ) -> list[BrokerDailyFlow]:
        """
        Fetch real per-day per-broker flow for a stock.

        Calls /order-trade/broker/activity/historical once per broker code with
        pagination (max 100 records/page). Returns one BrokerDailyFlow per
        (date, broker_code) — never an aggregate.

        Args:
            ticker: Stock ticker symbol.
            broker_codes: Which broker codes to fetch. Defaults to TRACKED_BROKER_CODES.
            days: Max calendar days to look back (capped at 365 by the API).
        """
        token = self._get_token()
        codes = broker_codes if broker_codes is not None else TRACKED_BROKER_CODES
        all_flows: list[BrokerDailyFlow] = []

        for code in codes:
            flows = _fetch_broker_daily_flows_for_code(token, ticker, code, days)
            all_flows.extend(flows)
            logger.debug(
                "fetch_broker_daily_flows: %s/%s → %d records", ticker, code, len(flows)
            )

        logger.info(
            "fetch_broker_daily_flows: %s → %d total records across %d codes",
            ticker, len(all_flows), len(codes),
        )
        return all_flows


def _fetch_broker_daily_flows_for_code(
    token: str,
    ticker: str,
    broker_code: str,
    days: int,
) -> list[BrokerDailyFlow]:
    """
    Fetch all daily flow records for one broker code on one ticker, with pagination.

    The API caps at 100 records per page (confirmed 2026-06-14). Uses has_next
    to determine when to stop. Stops early if the oldest returned date is older
    than `days` back from today.
    """
    from datetime import date as date_type
    from datetime import timedelta

    cutoff = date_type.today() - timedelta(days=days)
    page = 1
    results: list[BrokerDailyFlow] = []
    broker_name = broker_code  # default; overwritten from first response

    while True:
        url = (
            f"{_BROKER_HISTORICAL_API}"
            f"?broker_codes={broker_code}"
            f"&symbols={ticker.upper()}"
            f"&market_board=BOARD_TYPE_REGULAR"
            f"&investor_type=INVESTOR_TYPE_ALL"
            f"&interval=INTERVAL_DAILY"
            f"&period=RT_PERIOD_LAST_1_YEAR"
            f"&pagination.page={page}"
            f"&pagination.limit=100"
        )
        body = _exodus_get(url, token)
        if not body:
            break

        data = body.get("data") or {}
        # broker_name is only present when a single code is requested
        if data.get("broker_name"):
            broker_name = data["broker_name"]

        records = data.get("records") or []
        if not records:
            break

        for item in records:
            if not isinstance(item, dict):
                continue
            date_str = str(item.get("date") or "")
            try:
                flow_date = date_type.fromisoformat(date_str[:10])
            except (ValueError, TypeError):
                continue

            if flow_date < cutoff:
                return results  # older than requested window — stop paginating

            trade = item.get("trade_activity") or {}
            buy = trade.get("buy_summary") or {}
            sell = trade.get("sell_summary") or {}
            net = trade.get("net_summary") or {}
            total_buy = trade.get("total_buy_lot") or {}
            total_sell = trade.get("total_sell_lot") or {}

            buy_lot = _dict_int(buy, "lot") or 0
            sell_lot = _dict_int(sell, "lot") or 0
            net_lot = _dict_int(net, "lot") or 0
            buy_value = _dict_dec(buy, "value")
            sell_value = _dict_dec(sell, "value")
            net_value = _dict_dec(net, "value")
            avg_buy_price = _dict_dec(buy, "avg_price")
            avg_sell_price = _dict_dec(sell, "avg_price")
            avg_price = _dict_dec(net, "avg_price")

            try:
                results.append(BrokerDailyFlow(
                    ticker=ticker.upper(),
                    date=flow_date,
                    broker_code=broker_code.upper(),
                    broker_name=broker_name,
                    source="stockbit",
                    buy_lot=abs(buy_lot),
                    sell_lot=abs(sell_lot),
                    net_lot=net_lot,
                    buy_value=abs(buy_value),
                    sell_value=abs(sell_value),
                    net_value=net_value,
                    avg_buy_price=avg_buy_price,
                    avg_sell_price=avg_sell_price,
                    avg_price=avg_price,
                    buy_pct=float(total_buy.get("pct") or 0),
                    sell_pct=float(total_sell.get("pct") or 0),
                ))
            except Exception as e:
                logger.debug("Could not parse BrokerDailyFlow %s/%s %s: %s",
                             ticker, broker_code, date_str, e)

        pagination = data.get("pagination") or {}
        if not pagination.get("has_next"):
            break
        page += 1

    return results


def _dict_int(d: dict | None, *keys: str) -> int:
    """Extract an integer from a dict, trying multiple key names."""
    for k in keys:
        v = (d or {}).get(k)
        if v is not None:
            try:
                return int(float(str(v)))
            except (ValueError, TypeError):
                pass
    return 0


def _dict_dec(d: dict | None, *keys: str) -> Decimal:
    """Extract a Decimal from a dict, trying multiple key names."""
    for k in keys:
        v = (d or {}).get(k)
        if v is not None:
            try:
                return Decimal(str(v))
            except Exception:
                pass
    return Decimal("0")


def _parse_broker_tx(item: dict) -> BrokerTransaction | None:
    """
    Parse a single named-broker row from a marketdetectors response item.

    Handles two common shapes:
      Shape A (nested):  item.buy.lot / item.sell.lot
      Shape B (flat):    item.buy_lot / item.sell_lot
    """
    broker_node = item.get("broker") or {}
    code = (
        broker_node.get("code")
        or item.get("broker_code")
        or item.get("code")
        or ""
    )
    name = broker_node.get("name") or item.get("broker_name") or item.get("name") or code
    if not code:
        return None

    inv_type = (item.get("investor_type") or "").upper()
    if "FOREIGN" in inv_type or "ASING" in inv_type:
        broker_type = BrokerType.FOREIGN
    elif "LOCAL" in inv_type or "LOKAL" in inv_type or "DOMESTIC" in inv_type:
        broker_type = BrokerType.LOCAL
    else:
        broker_type = BrokerType.UNKNOWN

    buy_node = item.get("buy") or {}
    sell_node = item.get("sell") or {}

    buy_lot = _dict_int(buy_node, "lot", "lots") or _dict_int(item, "buy_lot")
    sell_lot = _dict_int(sell_node, "lot", "lots") or _dict_int(item, "sell_lot")
    buy_val = _dict_dec(buy_node, "value") or _dict_dec(item, "buy_value")
    sell_val = _dict_dec(sell_node, "value") or _dict_dec(item, "sell_value")
    avg_buy = _dict_dec(buy_node, "avg_price", "avg") or _dict_dec(item, "avg_buy_price")
    avg_sell = _dict_dec(sell_node, "avg_price", "avg") or _dict_dec(item, "avg_sell_price")

    try:
        return BrokerTransaction(
            broker_code=str(code).upper(),
            broker_name=str(name),
            broker_type=broker_type,
            buy_lot=abs(buy_lot),
            sell_lot=abs(sell_lot),
            buy_value=abs(buy_val),
            sell_value=abs(sell_val),
            avg_buy_price=avg_buy,
            avg_sell_price=avg_sell,
        )
    except Exception as e:
        logger.debug("Could not parse broker tx %s: %s", code, e)
        return None


def _parse_historical_summary_flow(
    ticker: str,
    body: dict,
) -> list[ForeignFlowPoint]:
    """
    Extract per-day ForeignFlowPoint from /company-price-feed/historical/summary response.

    Confirmed response shape (2026-06-20):
      data.result[].date         → "YYYY-MM-DD"
      data.result[].foreign_buy  → int IDR
      data.result[].foreign_sell → int IDR
      data.result[].net_foreign  → int IDR
      data.result[].volume       → int lots (total volume, used as proxy for net_lot)
      data.result[].close        → float (close price)
    """
    rows = (body.get("data") or {}).get("result") or []
    points: list[ForeignFlowPoint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            d = date.fromisoformat(str(row.get("date") or "")[:10])
        except (ValueError, TypeError):
            continue
        net_val = Decimal(str(row.get("net_foreign") or 0))
        net_lot = int(row.get("volume") or 0)
        close_price = Decimal(str(row.get("close") or 0))
        points.append(ForeignFlowPoint(
            ticker=ticker.upper(),
            date=d,
            net_val=net_val,
            net_lot=net_lot,
            avg_price=close_price,
            source="stockbit_summary",
        ))
    return sorted(points, key=lambda p: p.date)


def _fetch_historical_summary_totals(
    ticker: str,
    start_date: date,
    end_date: date,
    token: str,
) -> tuple[Decimal, int] | None:
    """
    Return (total_value_IDR, total_lot) from /company-price-feed/historical/summary/{ticker}.

    Sums all daily rows in [start_date, end_date]. Returns None on any failure so
    the caller can fall back to the synthetic marketdetectors total.

    Confirmed response shape (live probe 2026-06-20):
      data.result[].value  → total traded value (IDR, int)
      data.result[].volume → total traded lots (int, already in lots — NOT shares)
    """
    total_value = Decimal("0")
    total_lot = 0
    page = 1
    has_rows = False

    try:
        while True:
            url = (
                f"{_HISTORICAL_SUMMARY_API.format(ticker=ticker.upper())}"
                f"?period=HS_PERIOD_DAILY"
                f"&start_date={start_date.isoformat()}"
                f"&end_date={end_date.isoformat()}"
                f"&limit=50&page={page}"
            )
            body = _exodus_get(url, token)
            if not body:
                break
            rows = (body.get("data") or {}).get("result") or []
            if not rows:
                break
            has_rows = True
            for r in rows:
                if isinstance(r, dict):
                    total_value += Decimal(str(r.get("value") or 0))
                    total_lot += int(r.get("volume") or 0)
            if len(rows) < 50:
                break
            page += 1

        if not has_rows or total_value <= 0:
            return None
        return total_value, total_lot
    except Exception as e:
        logger.debug("historical/summary totals failed for %s: %s", ticker, e)
        return None



def _parse_marketdetectors_response(
    ticker: str,
    trading_date: date,
    body: dict,
    real_total: tuple[Decimal, int] | None = None,
) -> list[BrokerSummary]:
    """
    Parse the stock-centric /marketdetectors/{ticker} response into a BrokerSummary.

    Confirmed response shape (2026-06-13):
      data.broker_summary.brokers_buy[]  — net buyer rows
        netbs_broker_code, blot, bval, netbs_buy_avg_price, type, netbs_date (YYYYMMDD)
      data.broker_summary.brokers_sell[] — net seller rows
        netbs_broker_code, slot (neg), sval (neg), netbs_sell_avg_price, type
    """
    data = body.get("data") if isinstance(body, dict) else body
    if not isinstance(data, dict):
        return []

    broker_summary = data.get("broker_summary") or {}
    if not isinstance(broker_summary, dict):
        return []

    buy_items: list = broker_summary.get("brokers_buy") or []
    sell_items: list = broker_summary.get("brokers_sell") or []

    if not buy_items and not sell_items:
        logger.debug("marketdetectors/%s: no brokers_buy/brokers_sell in response", ticker)
        return []

    def _broker_type(item: dict) -> BrokerType:
        return BrokerType.FOREIGN if item.get("type") == "Asing" else BrokerType.LOCAL

    def _parse_yyyymmdd(s: str) -> date:
        """Parse YYYYMMDD date string."""
        s = str(s or "").strip()
        if len(s) == 8:
            try:
                return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
            except (ValueError, TypeError):
                pass
        return trading_date

    buyers: list[BrokerTransaction] = []
    for item in buy_items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("netbs_broker_code") or "").strip()
        if not code:
            continue
        try:
            buyers.append(BrokerTransaction(
                broker_code=code,
                broker_name=code,
                broker_type=_broker_type(item),
                buy_lot=abs(_dict_int(item, "blot")),
                sell_lot=0,
                buy_value=abs(_dict_dec(item, "bval")),
                sell_value=Decimal("0"),
                avg_buy_price=_dict_dec(item, "netbs_buy_avg_price"),
                avg_sell_price=Decimal("0"),
            ))
        except Exception as e:
            logger.debug("Could not parse buy broker %s: %s", code, e)

    sellers: list[BrokerTransaction] = []
    for item in sell_items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("netbs_broker_code") or "").strip()
        if not code:
            continue
        try:
            sellers.append(BrokerTransaction(
                broker_code=code,
                broker_name=code,
                broker_type=_broker_type(item),
                buy_lot=0,
                sell_lot=abs(_dict_int(item, "slot")),
                buy_value=Decimal("0"),
                sell_value=abs(_dict_dec(item, "sval")),
                avg_buy_price=Decimal("0"),
                avg_sell_price=_dict_dec(item, "netbs_sell_avg_price"),
            ))
        except Exception as e:
            logger.debug("Could not parse sell broker %s: %s", code, e)

    if not buyers and not sellers:
        return []

    # Actual trading date from first item (YYYYMMDD field)
    first_item = buy_items[0] if buy_items else sell_items[0]
    actual_date = _parse_yyyymmdd(first_item.get("netbs_date", ""))

    all_txns = buyers + sellers
    foreign_txns = [t for t in all_txns if t.is_foreign]

    foreign_buy_val = sum((t.buy_value for t in foreign_txns), Decimal("0"))
    foreign_sell_val = sum((t.sell_value for t in foreign_txns), Decimal("0"))
    foreign_buy_lot = sum(t.buy_lot for t in foreign_txns)
    foreign_sell_lot = sum(t.sell_lot for t in foreign_txns)

    if real_total is not None:
        total_val, total_lot = real_total
    else:
        total_val = sum((t.buy_value + t.sell_value for t in all_txns), Decimal("0"))
        total_lot = sum(t.buy_lot + t.sell_lot for t in all_txns)
        logger.warning(
            "marketdetectors/%s: using synthetic total_value (historical/summary unavailable)",
            ticker,
        )

    try:
        return [BrokerSummary(
            ticker=ticker.upper(),
            date=actual_date,
            top_buyers=tuple(buyers[:10]),
            top_sellers=tuple(sellers[:10]),
            foreign_buy_value=foreign_buy_val,
            foreign_sell_value=foreign_sell_val,
            foreign_buy_lot=foreign_buy_lot,
            foreign_sell_lot=foreign_sell_lot,
            total_value=total_val,
            total_lot=total_lot,
            source="stockbit",
        )]
    except Exception as e:
        logger.debug("Could not build BrokerSummary for %s: %s", ticker, e)
        return []


def _parse_nval_trend(ticker: str, trend_raw: list) -> tuple[ForeignFlowPoint, ...]:
    """Parse nval_trend[] array embedded in broker activity universe scan items."""
    points: list[ForeignFlowPoint] = []
    for row in trend_raw or []:
        if not isinstance(row, dict):
            continue
        try:
            d = date.fromisoformat(str(row.get("date") or "")[:10])
            net_val = Decimal(str(row.get("nval") or 0))
            net_lot = int(row.get("nvol") or 0)
            points.append(ForeignFlowPoint(
                ticker=ticker,
                date=d,
                net_val=net_val,
                net_lot=net_lot,
                avg_price=Decimal(str(row.get("close") or 0)),
                source="stockbit_trend",
            ))
        except Exception:
            pass
    return tuple(sorted(points, key=lambda p: p.date))


def _parse_foreign_top_stocks(
    snapshot_date: date,
    body: dict,
) -> list[ForeignFlowSnapshot]:
    """
    Parse the broker-centric /order-trade/broker/activity response.

    Confirmed response shape (2026-06-13):
      data.broker_activity_transaction.brokers_buy[]  — net buyer stocks
        stock_code, value (net val), lot, avg_price, type, nval_trend[]
      data.broker_activity_transaction.brokers_sell[] — net seller stocks
        stock_code, value (negative), lot (negative), avg_price, type, nval_trend[]
    """
    data = body.get("data") if isinstance(body, dict) else body
    if not isinstance(data, dict):
        return []

    txn = data.get("broker_activity_transaction") or {}
    if not isinstance(txn, dict):
        logger.debug("_parse_foreign_top_stocks: no broker_activity_transaction in response")
        return []

    buy_items: list = txn.get("brokers_buy") or []
    sell_items: list = txn.get("brokers_sell") or []

    snapshots: list[ForeignFlowSnapshot] = []
    seen: set[str] = set()

    for item in buy_items:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("stock_code") or "").upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        try:
            net_val = _dict_dec(item, "value")
            net_lot = _dict_int(item, "lot")
            item_date_str = str(item.get("date") or "")
            try:
                item_date = date.fromisoformat(item_date_str[:10])
            except (ValueError, TypeError):
                item_date = snapshot_date
            nval_trend = _parse_nval_trend(ticker, item.get("nval_trend") or [])
            snapshots.append(ForeignFlowSnapshot(
                ticker=ticker,
                date=item_date,
                net_val=net_val,
                net_lot=net_lot,
                nval_trend=nval_trend,
            ))
        except Exception as e:
            logger.debug("Could not parse foreign flow snapshot for %s: %s", ticker, e)

    for item in sell_items:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("stock_code") or "").upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        try:
            # sell values are negative in the response
            net_val = _dict_dec(item, "value")
            net_lot = _dict_int(item, "lot")
            item_date_str = str(item.get("date") or "")
            try:
                item_date = date.fromisoformat(item_date_str[:10])
            except (ValueError, TypeError):
                item_date = snapshot_date
            nval_trend = _parse_nval_trend(ticker, item.get("nval_trend") or [])
            snapshots.append(ForeignFlowSnapshot(
                ticker=ticker,
                date=item_date,
                net_val=net_val,
                net_lot=net_lot,
                nval_trend=nval_trend,
            ))
        except Exception as e:
            logger.debug("Could not parse foreign flow snapshot for %s: %s", ticker, e)

    return sorted(snapshots, key=lambda s: abs(s.net_val), reverse=True)


def _parse_foreign_flow_history(
    ticker: str,
    body: dict,
) -> list[ForeignFlowPoint]:
    """
    Parse the stock-centric /order-trade/broker/activity/historical response.

    Confirmed response shape (2026-06-13):
      data.records[].date                              — "YYYY-MM-DD"
      data.records[].trade_activity.net_summary.lot   — net lot (can be negative)
      data.records[].trade_activity.net_summary.value — net value (can be negative)
      data.records[].trade_activity.net_summary.avg_price
      data.records[].price_activity.close_price       — fallback price
    """
    data = body.get("data") if isinstance(body, dict) else body
    if not isinstance(data, dict):
        return []

    rows = data.get("records")
    if not isinstance(rows, list) or not rows:
        logger.debug("broker_flow_history/%s: no 'records' list in response", ticker)
        return []

    points: list[ForeignFlowPoint] = []
    for item in rows:
        if not isinstance(item, dict):
            continue

        date_str = str(item.get("date") or "")
        try:
            point_date = date.fromisoformat(date_str[:10])
        except (ValueError, TypeError):
            continue

        trade = item.get("trade_activity") or {}
        net = trade.get("net_summary") or {}
        price_activity = item.get("price_activity") or {}

        net_val = _dict_dec(net, "value")
        net_lot = _dict_int(net, "lot")
        avg_price = _dict_dec(net, "avg_price") or _dict_dec(price_activity, "close_price")

        try:
            points.append(ForeignFlowPoint(
                ticker=ticker.upper(),
                date=point_date,
                net_val=net_val,
                net_lot=net_lot,
                avg_price=avg_price,
            ))
        except Exception as e:
            logger.debug("Could not parse flow point for %s %s: %s", ticker, date_str, e)

    return sorted(points, key=lambda p: p.date)


def _parse_broker_flow_history(
    ticker: str,
    body: dict,
) -> list[BrokerFlowPoint]:
    """Deprecated alias for _parse_foreign_flow_history."""
    return _parse_foreign_flow_history(ticker, body)


# ── Board-aware IEV fetcher ────────────────────────────────────────────────

def _fetch_iev_all_boards(token: str) -> list[MoverData]:
    """
    Call IEV movers API for both board groups, merge, deduplicate, sort by IEV desc.

    Mirrors how the Stockbit frontend works: two separate API calls (main boards
    and special monitoring board), then combined into one sorted list.

    Raises StockbitSessionExpired if any call returns 401.
    """
    seen: dict[str, MoverData] = {}

    for url in (_IEV_MOVER_URL_MAIN, _IEV_MOVER_URL_SPECIAL):
        body = _exodus_get(url, token)  # raises StockbitSessionExpired on 401
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


# ── API response parsers ────────────────────────────────────────────────────

def _parse_iev_response(body: dict, iev_min: int) -> list[MoverData]:
    """
    Parse IEV movers from the Exodus market-mover API response.

    Confirmed response shape (2026-06-13):
      data.mover_list[].stock_detail.code       → ticker
      data.mover_list[].iepiev_detail.iev.raw   → IEV as integer
      data.mover_list[].iepiev_detail.iep.raw   → IEP as integer, when present
    """
    movers: list[MoverData] = []

    # Primary path: data.mover_list
    mover_list = (body.get("data") or {}).get("mover_list")
    if isinstance(mover_list, list):
        for item in mover_list:
            if not isinstance(item, dict):
                continue
            ticker = _extract_ticker_confirmed(item)
            iev = _extract_iev_confirmed(item)
            iep = _extract_iep_confirmed(item)
            if ticker and iev is not None and iev >= iev_min:
                movers.append(MoverData(ticker=ticker, iev=iev, iep=iep))
        if movers:
            return sorted(movers, key=lambda m: m.iev, reverse=True)

    # Fallback: generic traversal (handles API shape changes)
    payload = body
    for key in ("data", "result", "movers", "items"):
        if isinstance(payload, dict) and key in payload:
            candidate = payload[key]
            if isinstance(candidate, list):
                payload = candidate
                break

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            ticker = _extract_ticker(item)
            iev = _extract_iev_from_mover(item)
            iep = _extract_iep_from_mover(item)
            if ticker and iev is not None and iev >= iev_min:
                movers.append(MoverData(ticker=ticker, iev=iev, iep=iep))

    return sorted(movers, key=lambda m: m.iev, reverse=True)


def _extract_ticker_confirmed(item: dict) -> str | None:
    """Extract ticker from confirmed Exodus mover_list item shape."""
    code = (item.get("stock_detail") or {}).get("code")
    if isinstance(code, str) and 2 <= len(code) <= 6:
        return code.upper()
    return _extract_ticker(item)  # fallback


def _extract_iev_confirmed(item: dict) -> int | None:
    """Extract IEV from confirmed Exodus mover_list item shape."""
    raw = (item.get("iepiev_detail") or {}).get("iev", {}).get("raw")
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return _extract_iev_from_mover(item)  # fallback


def _extract_iep_confirmed(item: dict) -> int | None:
    """Try to extract IEP from iepiev_detail.iep.raw (field presence unconfirmed — may be absent).

    IEP = Indicative Equilibrium Price, the expected call-auction clearing price in IDR.
    Returns None gracefully if the field does not exist in the response.
    """
    raw = (item.get("iepiev_detail") or {}).get("iep", {}).get("raw")
    if raw is not None:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return None


def _extract_iep_from_mover(item: dict) -> int | None:
    """Extract IEP value from generic mover payloads."""
    for key in ("iep", "IEP", "indicative_equilibrium_price", "equilibrium_price"):
        val = item.get(key)
        if val is not None:
            try:
                return int(float(str(val).replace(",", "")))
            except (ValueError, TypeError):
                pass
    for nested_key in ("stock", "data", "detail", "iepiev_detail"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            result = _extract_iep_from_mover(nested)
            if result is not None:
                return result
    return None


def _extract_iev_from_mover(item: dict) -> int | None:
    """Extract IEV value — generic fallback for unknown response shapes."""
    for key in ("iev", "IEV", "intraday_expected_volume", "ie_volume",
                "expected_volume", "volume_iev"):
        val = item.get(key)
        if val is not None:
            try:
                return int(float(str(val).replace("K", "e3").replace("M", "e6")))
            except (ValueError, TypeError):
                pass
    for nested_key in ("stock", "data", "detail", "iepiev_detail"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            result = _extract_iev_from_mover(nested)
            if result is not None:
                return result
    return None


def _parse_order_book_response(body: dict) -> OrderBookTopOfBook | None:
    """
    Parse order book API response from Exodus.
    Uses confirmed company-price-feed/v2/orderbook response shape.
    Returns both bid and offer sides.
    """
    bid_price, bid_lots, offer_price, offer_lots = _parse_top_of_book(body)
    bid = OrderBookBid(price=bid_price, volume=bid_lots) if bid_price and bid_lots else None
    offer = OrderBookBid(price=offer_price, volume=offer_lots) if offer_price and offer_lots else None
    if bid is None and offer is None:
        return None
    return OrderBookTopOfBook(bid=bid, offer=offer)


def _parse_top_of_book(
    body: dict | None,
) -> tuple[Decimal | None, int | None, Decimal | None, int | None]:
    """
    Extract best bid and best offer from a company-price-feed/v2/orderbook response.

    Returns (bid_price, bid_lots, offer_price, offer_lots).

    Confirmed response shape (2026-06-13):
      data.iepiev.best_bid_offer.bid.price.raw      → best bid price (int)
      data.iepiev.best_bid_offer.bid.quantity.raw   → best bid lots (int, already in lots)
      data.iepiev.best_bid_offer.offer.price.raw    → best offer price (int)
      data.iepiev.best_bid_offer.offer.quantity.raw → best offer lots (int, already in lots)

    The data.bid[] / data.offer[] lists contain full depth (price as string, volume in shares).
    The iepiev.best_bid_offer represents the pre-open equilibrium top-of-book.
    """
    if not body:
        return None, None, None, None

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None, None, None, None

    # Primary: iepiev.best_bid_offer (confirmed, values already in lots)
    bbo = (data.get("iepiev") or {}).get("best_bid_offer") or {}
    bid_raw = (bbo.get("bid") or {})
    offer_raw = (bbo.get("offer") or {})

    bid_price = _safe_decimal((bid_raw.get("price") or {}).get("raw"))
    bid_lots = _safe_int((bid_raw.get("quantity") or {}).get("raw"))
    offer_price = _safe_decimal((offer_raw.get("price") or {}).get("raw"))
    offer_lots = _safe_int((offer_raw.get("quantity") or {}).get("raw"))

    # If iepiev is missing/zero, fall back to data.bid[0] / data.offer[0]
    # Note: volume in bid/offer list is shares; divide by 100 for lots.
    if bid_price is None or bid_price == 0:
        bid_list = data.get("bid") or []
        if bid_list and isinstance(bid_list[0], dict):
            entry = bid_list[0]
            bid_price = _safe_decimal(entry.get("price"))
            shares = _safe_int(entry.get("volume"))
            bid_lots = (shares // 100) if shares else None

    if offer_price is None or offer_price == 0:
        offer_list = data.get("offer") or []
        if offer_list and isinstance(offer_list[0], dict):
            entry = offer_list[0]
            offer_price = _safe_decimal(entry.get("price"))
            shares = _safe_int(entry.get("volume"))
            offer_lots = (shares // 100) if shares else None

    # Fallback 3: NCP call auction — bid/offer lists empty while exchange locks orders.
    # iepiev.iep.raw is the exchange's own clearing price; use it as synthetic bid.
    # Safe: iep.raw is 0 outside NCP, so _safe_decimal rejects it → no effect.
    if bid_price is None or bid_price == 0:
        iep_raw = (data.get("iepiev") or {}).get("iep", {}).get("raw")
        iep_price = _safe_decimal(iep_raw)
        if iep_price:
            bid_price = iep_price

    return bid_price, bid_lots, offer_price, offer_lots


def _safe_decimal(val) -> Decimal | None:
    if val is None:
        return None
    try:
        d = Decimal(str(val))
        return d if d > 0 else None
    except (InvalidOperation, TypeError):
        return None


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _find_side_list(obj: Any, keys: tuple[str, ...], depth: int = 0) -> list | None:
    """Recursively search for a named list (bid side or offer side) in JSON."""
    if depth > 5 or not isinstance(obj, dict):
        return None
    for key in keys:
        val = obj.get(key) or obj.get(key.upper())
        if isinstance(val, list) and val:
            return val
    for v in obj.values():
        result = _find_side_list(v, keys, depth + 1)
        if result:
            return result
    return None


def _parse_movers_from_api(
    responses: list[dict], iev_min: int
) -> list[MoverData]:
    """
    Attempt to extract MoverData from captured API responses.

    Tries common response shapes. Run `saham fetch stockbit spy` to see the
    actual shape and update this function accordingly.
    """
    movers: list[MoverData] = []

    for resp in responses:
        body = resp.get("body")
        if not isinstance(body, dict):
            continue

        # Try to find a list field that looks like movers
        candidates = _find_list_in_json(body)
        for item_list in candidates:
            for item in item_list:
                if not isinstance(item, dict):
                    continue
                ticker = _extract_ticker(item)
                iev = _extract_iev(item)
                if ticker and iev is not None and iev >= iev_min:
                    movers.append(MoverData(ticker=ticker, iev=iev))

        if movers:
            break

    return sorted(movers, key=lambda m: m.iev, reverse=True)


def _parse_best_bid_from_api(
    responses: list[dict], ticker: str
) -> OrderBookBid | None:
    """
    Attempt to extract best bid from captured order book API responses.

    Tries common response shapes. Run `saham fetch stockbit spy` to see the
    actual shape and update this function accordingly.
    """
    for resp in responses:
        body = resp.get("body")
        if not isinstance(body, dict):
            continue

        bid = _find_best_bid_in_json(body)
        if bid:
            return bid

    return None


def _find_list_in_json(obj: Any, depth: int = 0) -> list[list]:
    """Recursively find all list values in a JSON object."""
    if depth > 4:
        return []
    results = []
    if isinstance(obj, list) and len(obj) > 0:
        results.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            results.extend(_find_list_in_json(v, depth + 1))
    return results


def _extract_ticker(item: dict) -> str | None:
    """Try common field names for ticker symbol."""
    for key in ("symbol", "ticker", "stock_code", "kode", "code", "emiten"):
        val = item.get(key) or item.get(key.upper())
        if isinstance(val, str) and 2 <= len(val) <= 6:
            return val.upper()
    return None


def _extract_iev(item: dict) -> int | None:
    """Try common field names for IEV."""
    for key in ("iev", "IEV", "intraday_expected_volume", "expected_volume",
                "pre_open_volume", "volume_expected"):
        val = item.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None


def _find_best_bid_in_json(obj: Any, depth: int = 0) -> OrderBookBid | None:
    """Recursively search for bid data in an order book response."""
    if depth > 5:
        return None

    if isinstance(obj, dict):
        # Look for a "bid" key containing a list
        for key in ("bid", "buy", "bids", "buys", "buyer"):
            val = obj.get(key) or obj.get(key.upper())
            if isinstance(val, list) and val:
                best = _best_bid_from_list(val)
                if best:
                    return best

        # Recurse
        for v in obj.values():
            result = _find_best_bid_in_json(v, depth + 1)
            if result:
                return result

    elif isinstance(obj, list):
        best = _best_bid_from_list(obj)
        if best:
            return best

    return None


def _best_bid_from_list(items: list) -> OrderBookBid | None:
    """Find the bid entry with the largest volume from a list of dicts."""
    best_price: Decimal | None = None
    best_volume: int = 0

    for item in items:
        if not isinstance(item, dict):
            continue
        price = _extract_price(item)
        volume = _extract_volume(item)
        if price is not None and volume is not None and volume > best_volume:
            best_price = price
            best_volume = volume

    if best_price is not None and best_volume > 0:
        return OrderBookBid(price=best_price, volume=best_volume)
    return None


def _extract_price(item: dict) -> Decimal | None:
    for key in ("price", "harga", "last_price", "bid_price", "p"):
        val = item.get(key) or item.get(key.upper())
        if val is not None:
            try:
                return Decimal(str(val))
            except (InvalidOperation, TypeError):
                pass
    return None


def _extract_volume(item: dict) -> int | None:
    # Stockbit orderbook uses "lot" as the column name (visible in UI)
    for key in ("lot", "lots", "volume", "qty", "quantity", "vol", "v"):
        val = item.get(key) or item.get(key.upper())
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    return None


# ── DOM scrapers (fallback) ────────────────────────────────────────────────

def _scrape_movers_from_dom(page: Any, iev_min: int) -> list[MoverData]:
    """
    DOM fallback for movers. Tries multiple selector strategies.
    Needs calibration against actual Stockbit DOM after `saham fetch stockbit spy`.
    """
    movers: list[MoverData] = []

    # Strategy 1: standard table
    rows = page.query_selector_all("table tbody tr")
    if rows:
        for row in rows:
            cells = row.query_selector_all("td")
            if len(cells) < 2:
                continue
            try:
                ticker_text = cells[0].inner_text().strip().upper()
                # IEV may be in any column — try each one
                for cell in cells[1:]:
                    raw = cell.inner_text().strip()
                    iev = _parse_number(raw)
                    if iev and iev >= iev_min and 2 <= len(ticker_text) <= 6:
                        movers.append(MoverData(ticker=ticker_text, iev=iev))
                        break
            except Exception:
                continue

    if movers:
        return sorted(movers, key=lambda m: m.iev, reverse=True)

    # Strategy 2: look for elements containing ticker-like text near numbers
    # (handles div-based layouts)
    logger.warning(
        "DOM scrape: no table rows found. "
        "Run 'saham fetch stockbit spy' to identify the correct selectors."
    )
    return []


def _scrape_best_bid_from_dom(page: Any, ticker: str) -> OrderBookBid | None:
    """DOM fallback for order book. Needs calibration via spy."""
    best_price: Decimal | None = None
    best_volume: int = 0

    rows = page.query_selector_all("table tbody tr")
    for row in rows:
        cells = row.query_selector_all("td")
        if len(cells) < 2:
            continue
        try:
            # Try cells[0]=price, cells[1]=volume
            price_raw = cells[0].inner_text().strip()
            vol_raw = cells[1].inner_text().strip()
            price = Decimal(re.sub(r"[^\d]", "", price_raw))
            volume = int(re.sub(r"[^\d]", "", vol_raw))
            if price > 0 and volume > best_volume:
                best_price = price
                best_volume = volume
        except Exception:
            continue

    if best_price:
        return OrderBookBid(price=best_price, volume=best_volume)

    logger.warning(
        "DOM scrape: no order book data found for %s. "
        "Run 'saham fetch stockbit spy --url orderbook --ticker %s'",
        ticker, ticker,
    )
    return None


# ── API patterns file (populated by spy) ──────────────────────────────────

def _load_api_patterns(path: Path) -> dict:
    """Load custom API patterns discovered by spy-session."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)

