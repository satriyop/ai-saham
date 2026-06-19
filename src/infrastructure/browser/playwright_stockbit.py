"""
Playwright-based Stockbit browser provider.

Two modes:
  1. API-intercept mode (preferred): hooks Playwright's network layer to
     capture JSON responses, bypassing fragile DOM selectors entirely.
  2. DOM-scrape mode (fallback): parses rendered HTML tables.

Flow:
  saham fetch stockbit login   → saves browser session cookies
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
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

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
    BrokerDataProviderError,
)
from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.value_objects.screener_result import MoverData, MoverWithOrderBook, OrderBookBid, OrderBookTopOfBook

logger = logging.getLogger(__name__)

DEFAULT_SESSION_FILE = Path("stockbit_session.json")  # legacy cookie file
DEFAULT_PROFILE_DIR = Path(".stockbit_profile")        # persistent browser profile

# ── Stockbit URLs ──────────────────────────────────────────────────────────
BASE_URL = "https://stockbit.com"
STREAM_URL = "https://stockbit.com/stream"       # kept for spy
SCREENER_URL = "https://stockbit.com/screener"   # kept for spy fallback
ORDER_BOOK_URL = "https://stockbit.com/stock/{ticker}/orderbook"
# Confirmed to fire Bearer-authenticated Exodus API calls immediately on load.
# stockbit.com/stream does NOT reliably fire Bearer requests within the settle window.
ORDERBOOK_PAGE_URL = "https://stockbit.com/orderbook"
LOGIN_URL = "https://stockbit.com/login"
EXODUS_API = "https://exodus.stockbit.com"

# ── Stockbit API config — driven by config/stockbit.yaml ─────────────────
# Edit config/stockbit.yaml to update endpoints or broker codes without
# touching Python source. Run `saham fetch stockbit spy` to discover new endpoints.

@dataclass(frozen=True)
class _StockbitConfig:
    """Runtime config for Stockbit API. All fields carry hardcoded defaults so
    the system works even when config/stockbit.yaml is absent or malformed."""

    iev_movers_main_url: str = (
        "https://exodus.stockbit.com/order-trade/market-mover"
        "?mover_type=MOVER_TYPE_IEV_TOP_GAINER"
        "&filter_stocks=FILTER_STOCKS_TYPE_MAIN_BOARD"
        "&filter_stocks=FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD"
        "&filter_stocks=FILTER_STOCKS_TYPE_ACCELERATION_BOARD"
        "&filter_stocks=FILTER_STOCKS_TYPE_NEW_ECONOMY_BOARD"
    )
    iev_movers_special_url: str = (
        "https://exodus.stockbit.com/order-trade/market-mover"
        "?mover_type=MOVER_TYPE_IEV_TOP_GAINER"
        "&filter_stocks=FILTER_STOCKS_TYPE_SPECIAL_MONITORING_BOARD"
    )
    orderbook_url: str = (
        "https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{ticker}"
    )
    marketdetectors_url: str = "https://exodus.stockbit.com/marketdetectors"
    broker_activity_url: str = "https://exodus.stockbit.com/order-trade/broker/activity"
    broker_historical_url: str = "https://exodus.stockbit.com/order-trade/broker/activity/historical"
    # 10 institutional proxy codes for foreign_flow_points aggregate.
    # YP (Indo Premier) is domestic but mirrors institutional orders.
    # For true all-foreign aggregate, use broker_summaries.foreign_net_value (IDX source).
    institutional_proxy_codes: tuple[str, ...] = (
        "AK", "ZP", "YP", "BK", "YU", "CP", "KZ", "HD", "RX", "DR"
    )
    # Per-identity broker codes. Call historical endpoint ONCE PER CODE.
    # CS excluded: Credit Suisse wound down Indonesian operations (confirmed 0 trades).
    tracked_broker_codes: tuple[str, ...] = (
        "AK", "ZP", "YP", "BK", "YU", "CP", "KZ", "HD", "RX", "DR",
        "XL", "PD", "MS", "DB", "ML",
    )


def _load_stockbit_config(
    config_path: Path = Path("config/stockbit.yaml"),
) -> _StockbitConfig:
    """Load Stockbit API config from YAML. Returns hardcoded defaults on any error."""
    defaults = _StockbitConfig()
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        return defaults

    try:
        eps = data.get("endpoints") or {}
        codes = data.get("broker_codes") or {}

        def _url(key: str, default: str) -> str:
            raw = (eps.get(key) or {}).get("url", "")
            return str(raw).strip() if raw else default

        def _codes(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
            raw = codes.get(key) or []
            parsed = tuple(str(c).strip().upper() for c in raw if c)
            return parsed if parsed else default

        return _StockbitConfig(
            iev_movers_main_url=_url("iev_movers_main", defaults.iev_movers_main_url),
            iev_movers_special_url=_url("iev_movers_special", defaults.iev_movers_special_url),
            orderbook_url=_url("orderbook", defaults.orderbook_url),
            marketdetectors_url=_url("broker_marketdetectors", defaults.marketdetectors_url),
            broker_activity_url=_url("broker_activity", defaults.broker_activity_url),
            broker_historical_url=_url("broker_historical", defaults.broker_historical_url),
            institutional_proxy_codes=_codes("institutional_proxy", defaults.institutional_proxy_codes),
            tracked_broker_codes=_codes("tracked", defaults.tracked_broker_codes),
        )
    except Exception:
        return defaults


# Populate module-level constants from config (falls back to _StockbitConfig defaults).
_sb = _load_stockbit_config()

# Confirmed Exodus API endpoints (originally from DevTools spy, 2026-06-13).
# Update via config/stockbit.yaml after running `saham fetch stockbit spy`.
_IEV_MOVER_URL_MAIN    = _sb.iev_movers_main_url
_IEV_MOVER_URL_SPECIAL = _sb.iev_movers_special_url
_ORDER_BOOK_API        = _sb.orderbook_url        # supports {ticker} placeholder
_MARKETDETECTORS_API   = _sb.marketdetectors_url
_BROKER_ACTIVITY_API   = _sb.broker_activity_url
_BROKER_HISTORICAL_API = _sb.broker_historical_url
_INSTITUTIONAL_PROXY_CODES = list(_sb.institutional_proxy_codes)
TRACKED_BROKER_CODES       = list(_sb.tracked_broker_codes)

# Spy navigation pages — each fires its respective endpoint immediately on load
_STOCK_BROKER_PAGE_URL = "https://stockbit.com/broker-analysis/stock"
_BROKER_ANALYSIS_PAGE_URL = "https://stockbit.com/broker-analysis/broker"

_BROKER_URL_PATTERNS = ["marketdetectors", "broker/activity", "activity/historical"]

# ── Timeouts (ms) ─────────────────────────────────────────────────────────
NAV_TIMEOUT = 30_000
ELEMENT_TIMEOUT = 15_000
SPA_SETTLE_MS = 4_000   # extra wait for React to render after navigation

# ── API endpoint patterns ──────────────────────────────────────────────────
# Base: exodus.stockbit.com (confirmed by spy session)
# IEV/movers endpoint still unknown — needs spy with valid Pro session.
_MOVERS_URL_PATTERNS = [
    "exodus.stockbit.com/screener",
    "exodus.stockbit.com/market/mover",
    "exodus.stockbit.com/pre-open",
    "exodus.stockbit.com/iev",
    "exodus.stockbit.com/stock/mover",
    "mover", "iev", "preopen",
]
_ORDERBOOK_URL_PATTERNS = [
    "company-price-feed/v2/orderbook",   # confirmed endpoint
    "exodus.stockbit.com/orderbook",
    "exodus.stockbit.com/order-book",
    "exodus.stockbit.com/stock",
    "orderbook", "order-book",
]


# ── Helpers ────────────────────────────────────────────────────────────────

def _require_playwright():
    """Import playwright or raise with install instructions."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed. Run:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )


def _load_session(session_file: Path) -> dict:
    """Load cookies + localStorage from saved session file."""
    if not session_file.exists():
        raise RuntimeError(
            f"No session file at '{session_file}'.\n"
            "Run: saham fetch stockbit login"
        )
    with open(session_file) as f:
        data = json.load(f)
    if not data.get("cookies") and not data.get("local_storage"):
        raise RuntimeError(
            f"Session file '{session_file}' appears empty.\n"
            "Run: saham fetch stockbit login to refresh."
        )
    return data


def _persistent_context(pw, profile_dir: Path, headless: bool = True):
    """
    Launch a persistent Chromium context using a saved browser profile.

    The profile directory stores ALL browser state (cookies, localStorage,
    IndexedDB, cache) exactly like a real Chrome profile. No cookie extraction
    or injection needed — the browser is simply already logged in.

    Args:
        pw: sync_playwright instance
        profile_dir: Path to the browser profile directory
        headless: Whether to run the browser headlessly

    Returns:
        (context, page) — context IS the browser; call context.close() when done.
    """
    profile_dir.mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        str(profile_dir),
        headless=headless,
        args=["--no-first-run", "--no-default-browser-check"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    return ctx, page


def _new_authenticated_context(pw, session_data: dict, headless: bool = True):
    """
    Create a Playwright browser + context with session pre-loaded.

    Cookies are injected into the context BEFORE any navigation so the first
    request to stockbit.com already carries auth cookies. localStorage is
    injected after a lightweight navigation to the domain.

    Returns (browser, context, page) — caller is responsible for browser.close().
    """
    cookies = session_data.get("cookies", [])
    local_storage = session_data.get("local_storage", {})
    session_storage = session_data.get("session_storage", {})

    browser = pw.chromium.launch(headless=headless)
    ctx = browser.new_context()

    # Step 1: inject cookies onto context BEFORE any navigation
    if cookies:
        ctx.add_cookies(cookies)

    page = ctx.new_page()

    # Step 2: navigate to domain so localStorage can be written
    if local_storage or session_storage:
        page.goto(BASE_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        if local_storage:
            try:
                page.evaluate(
                    """(data) => {
                        for (const [k, v] of Object.entries(data)) {
                            try { localStorage.setItem(k, v); } catch(e) {}
                        }
                    }""",
                    local_storage,
                )
            except Exception as e:
                logger.debug("Could not inject localStorage: %s", e)
        if session_storage:
            try:
                page.evaluate(
                    """(data) => {
                        for (const [k, v] of Object.entries(data)) {
                            try { sessionStorage.setItem(k, v); } catch(e) {}
                        }
                    }""",
                    session_storage,
                )
            except Exception as e:
                logger.debug("Could not inject sessionStorage: %s", e)

    return browser, ctx, page


def _url_matches(url: str, patterns: list[str]) -> bool:
    url_lower = url.lower()
    return any(p in url_lower for p in patterns)


def _intercept_token(page) -> list[str]:
    """
    Register a request interceptor on page BEFORE navigation to capture
    the RS256 Bearer token Stockbit sends to exodus.stockbit.com.

    Returns a mutable list that will be populated as requests fire.
    Call _resolve_token() after the page settles to read it.
    """
    captured: list[str] = []

    def _on_req(request):
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer ") and "exodus.stockbit.com" in request.url:
            token = auth.removeprefix("Bearer ")
            if token not in captured:
                captured.append(token)

    try:
        page.on("request", _on_req)
    except Exception as e:
        logger.debug("Could not register token interceptor: %s", e)

    return captured


def _resolve_token(page, token_box: list[str]) -> str | None:
    """
    Return the first token captured by _intercept_token, falling back to
    _extract_jwt (localStorage) if no request-based token was captured yet.
    """
    if token_box:
        logger.debug("RS256 token from intercepted request (%d chars)", len(token_box[0]))
        return token_box[0]
    logger.debug("No intercepted token yet — trying localStorage fallback")
    return _extract_jwt(page)


def _extract_jwt(page) -> str | None:
    """
    Extract the API Bearer token by intercepting an outgoing Exodus request.

    The app uses two different JWTs: an HS256 token stored in localStorage
    (for in-app use) and an RS256 Bearer token sent to the Exodus API. Only
    the latter works for direct httpx calls, so we capture it from request headers.
    """
    captured: list[str] = []

    def _on_req(request):
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer ") and "exodus.stockbit.com" in request.url:
            captured.append(auth.removeprefix("Bearer "))

    try:
        page.on("request", _on_req)
        # Small wait for any pending requests already in-flight to arrive
        page.wait_for_timeout(2_000)
    except Exception as e:
        logger.debug("JWT intercept setup failed: %s", e)

    if captured:
        token = captured[0]
        logger.debug("JWT intercepted from request headers (%d chars)", len(token))
        return token

    # Fallback: localStorage HS256 token (may not work for all endpoints)
    try:
        token = page.evaluate("""
            () => {
                for (const key of Object.keys(localStorage)) {
                    const val = localStorage.getItem(key);
                    if (val && val.startsWith('eyJ')) return val;
                }
                return null;
            }
        """)
        if token:
            logger.debug("JWT from localStorage (HS256 — may be rejected by some endpoints)")
        return token
    except Exception as e:
        logger.debug("JWT localStorage fallback failed: %s", e)
        return None


class StockbitSessionExpired(RuntimeError):
    """Raised when the Exodus API rejects our token with 401."""


def _exodus_get(url: str, token: str) -> dict | None:
    """Make an authenticated GET to the Exodus API using httpx."""
    import httpx
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json, text/plain, */*",
        "x-platform": "web",
        "origin": "https://stockbit.com",
        "referer": "https://stockbit.com/",
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=15)
        if resp.status_code == 401:
            raise StockbitSessionExpired(
                "Stockbit API session expired (401). Run: saham fetch stockbit login"
            )
        resp.raise_for_status()
        return resp.json()
    except StockbitSessionExpired:
        raise
    except Exception as e:
        logger.debug("Exodus API call failed: %s — %s", url, e)
        return None


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
        session_file: Path = DEFAULT_SESSION_FILE,
        profile_dir: Path = DEFAULT_PROFILE_DIR,
        headless: bool = True,
        timeout: int = NAV_TIMEOUT,
        api_patterns_file: Path | None = None,
    ) -> None:
        self._session_file = session_file
        self._profile_dir = profile_dir
        self._headless = headless
        self._timeout = timeout
        self._api_patterns = _load_api_patterns(api_patterns_file) if api_patterns_file else {}

    def _use_persistent(self) -> bool:
        """Prefer persistent profile if it exists, fall back to cookie file."""
        return self._profile_dir.exists() and any(self._profile_dir.iterdir())

    def _assert_session_fresh(self) -> None:
        """Raise before launching a browser if the session marker is too old."""
        marker = self._profile_dir / ".logged_in_at"
        if not marker.exists():
            return  # no marker → let the browser try (legacy flow)
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
            if self._use_persistent():
                ctx, page = _persistent_context(pw, self._profile_dir, self._headless)
            else:
                session = _load_session(self._session_file)
                _, ctx, page = _new_authenticated_context(
                    pw, session, headless=self._headless
                )

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
            if self._use_persistent():
                ctx, page = _persistent_context(pw, self._profile_dir, self._headless)
            else:
                session = _load_session(self._session_file)
                _, ctx, page = _new_authenticated_context(
                    pw, session, headless=self._headless
                )

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
            if self._use_persistent():
                ctx, page = _persistent_context(pw, self._profile_dir, self._headless)
            else:
                session = _load_session(self._session_file)
                _, ctx, page = _new_authenticated_context(pw, session, headless=self._headless)

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
            if self._use_persistent():
                ctx, page = _persistent_context(pw, self._profile_dir, self._headless)
            else:
                session = _load_session(self._session_file)
                _, ctx, page = _new_authenticated_context(
                    pw, session, headless=self._headless
                )

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
                    logger.warning("Order book response parsed but no bid/offer found for %s", ticker)
                    logger.debug("Response: %s", str(body)[:500])
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

        summaries = _parse_marketdetectors_response(ticker, end_date, body)
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
    from datetime import date as date_type, timedelta

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


def _parse_marketdetectors_response(
    ticker: str,
    trading_date: date,
    body: dict,
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
    total_val = sum((t.buy_value + t.sell_value for t in all_txns), Decimal("0"))
    total_lot = sum(t.buy_lot + t.sell_lot for t in all_txns)

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


def _parse_foreign_top_stocks(
    snapshot_date: date,
    body: dict,
) -> list[ForeignFlowSnapshot]:
    """
    Parse the broker-centric /order-trade/broker/activity response.

    Confirmed response shape (2026-06-13):
      data.broker_activity_transaction.brokers_buy[]  — net buyer stocks
        stock_code, value (net val), lot, avg_price, type
      data.broker_activity_transaction.brokers_sell[] — net seller stocks
        stock_code, value (negative), lot (negative), avg_price, type
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
            snapshots.append(ForeignFlowSnapshot(
                ticker=ticker,
                date=item_date,
                net_val=net_val,
                net_lot=net_lot,
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
            snapshots.append(ForeignFlowSnapshot(
                ticker=ticker,
                date=item_date,
                net_val=net_val,
                net_lot=net_lot,
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


# ── Spy session ────────────────────────────────────────────────────────────

def spy_stockbit_session(
    session_file: Path = DEFAULT_SESSION_FILE,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    target: str = "screener",
    ticker: str = "BBCA",
    output_file: Path = Path("journals/stockbit-spy.json"),
    settle_ms: int = 6_000,
) -> dict:
    """
    Open Stockbit with the saved session, capture ALL API responses.

    Saves full request/response log to output_file for analysis.
    Use this to identify the correct API endpoints for movers and order book.

    Args:
        session_file: Path to saved session cookies
        target: 'screener' or 'orderbook'
        ticker: Ticker to use for order book target
        output_file: Where to save captured requests
        settle_ms: Milliseconds to wait for SPA to settle

    Returns:
        Summary dict with total_responses, unique_urls, output_file path
    """
    sync_playwright = _require_playwright()

    if target == "orderbook":
        url = ORDER_BOOK_URL.format(ticker=ticker.upper())
    elif target == "stock":
        # Named broker breakdown: loads marketdetectors/{ticker} on page open
        url = _STOCK_BROKER_PAGE_URL
    elif target == "stock-profile":
        # Company overview page — fires corporate action, financials, and price API calls.
        # Use this to discover the Exodus endpoint for dividend ex-date data.
        # Run: saham fetch stockbit spy --target stock-profile --ticker BBCA
        # Then inspect journals/stockbit-spy.json for corporate-action / dividen patterns.
        url = f"https://stockbit.com/stocks/{ticker.upper()}"
    elif target == "broker-scan":
        # Broker-centric universe scan: loads /order-trade/broker/activity on page open
        url = _BROKER_ANALYSIS_PAGE_URL
    elif target == "broker":
        # Legacy alias for stock (pre-2026-06-13)
        url = _STOCK_BROKER_PAGE_URL
    else:
        url = SCREENER_URL

    captured: list[dict] = []
    profile_exists = profile_dir.exists() and any(profile_dir.iterdir())

    with sync_playwright() as pw:
        if profile_exists:
            ctx, page = _persistent_context(pw, profile_dir, headless=False)
        else:
            session = _load_session(session_file)
            _, ctx, page = _new_authenticated_context(pw, session, headless=False)

        def on_response(response):
            ct = response.headers.get("content-type", "")
            entry: dict = {
                "url": response.url,
                "status": response.status,
                "content_type": ct,
                "body": None,
            }
            if "json" in ct:
                try:
                    entry["body"] = response.json()
                except Exception:
                    entry["body"] = "<parse error>"
            captured.append(entry)

        page.on("response", on_response)

        print(f"\nNavigating to: {url}")
        print(f"Capturing all network responses for {settle_ms // 1000}s...")
        print("The browser will open visibly so you can interact if needed.")
        print("Press Ctrl+C to stop early.\n")

        try:
            page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
            # Don't wait for networkidle — SPA pages never fully settle.
            # Just wait a fixed duration for API calls to fire.
            page.wait_for_timeout(settle_ms)
        except KeyboardInterrupt:
            pass
        finally:
            ctx.close()

    # Save full capture
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(captured, f, indent=2, default=str)

    # Build summary
    json_responses = [c for c in captured if "json" in c.get("content_type", "")]
    unique_urls = sorted(set(c["url"] for c in json_responses))

    # Flag URLs that might be relevant
    movers_hits = [u for u in unique_urls if _url_matches(u, _MOVERS_URL_PATTERNS)]
    orderbook_hits = [u for u in unique_urls if _url_matches(u, _ORDERBOOK_URL_PATTERNS)]
    broker_hits = [u for u in unique_urls if _url_matches(u, _BROKER_URL_PATTERNS)]

    return {
        "total_responses": len(captured),
        "json_responses": len(json_responses),
        "unique_json_urls": unique_urls,
        "movers_candidates": movers_hits,
        "orderbook_candidates": orderbook_hits,
        "broker_candidates": broker_hits,
        "output_file": str(output_file),
    }


# ── Browse (interactive session) ─────────────────────────────────────────────

def browse_stockbit_session(
    session_file: Path = DEFAULT_SESSION_FILE,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    url: str = STREAM_URL,
) -> None:
    """
    Open a headed browser with the saved Stockbit session and keep it open.

    Uses the persistent profile (.stockbit_profile/) if available, otherwise
    falls back to cookie injection from stockbit_session.json.

    The browser stays open until you press Ctrl+C or close it manually.

    Args:
        session_file: Legacy cookie file path (fallback if no profile)
        profile_dir: Persistent browser profile directory
        url: Stockbit page to open (default: stream/home)
    """
    sync_playwright = _require_playwright()
    profile_exists = profile_dir.exists() and any(profile_dir.iterdir())

    if profile_exists:
        print(f"Using persistent profile: {profile_dir}/")
    else:
        print(f"Using cookie session: {session_file}")

    print(f"Opening {url}")
    print("The browser will stay open until you press Ctrl+C.\n")

    with sync_playwright() as pw:
        if profile_exists:
            ctx, page = _persistent_context(pw, profile_dir, headless=False)
        else:
            session = _load_session(session_file)
            _, ctx, page = _new_authenticated_context(pw, session, headless=False)

        page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")

        try:
            while True:
                page.wait_for_timeout(10_000)
        except KeyboardInterrupt:
            print("\nClosing browser...")
        finally:
            ctx.close()


# ── Login / session management ─────────────────────────────────────────────

def save_stockbit_session(
    session_file: Path = DEFAULT_SESSION_FILE,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    timeout: int = 300,
) -> None:
    """
    Launch headed Chromium for manual Stockbit login.

    Uses a PERSISTENT browser profile (.stockbit_profile/) so all browser
    state (cookies, localStorage, IndexedDB) is preserved across runs —
    no cookie extraction/injection needed. The browser "stays logged in"
    exactly like a regular Chrome profile.

    Args:
        session_file: Legacy cookie file path (kept for backward compat)
        profile_dir: Persistent browser profile directory
        timeout: Seconds to wait for login completion
    """
    sync_playwright = _require_playwright()

    print("Opening Stockbit login page in a browser window.")
    print(f"Please log in manually. You have {timeout} seconds.")
    if timeout < 180:
        print("Tip: use --timeout 300 if you have 2FA enabled.")
    print(f"Browser profile: {profile_dir}  (stays logged in across runs)\n")

    with sync_playwright() as pw:
        ctx, page = _persistent_context(pw, profile_dir, headless=False)
        # domcontentloaded avoids hanging on SPA navigation
        page.goto(LOGIN_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")

        logged_in = False

        # Pages that are part of the auth flow — keep waiting while on any of these
        _AUTH_FLOW_FRAGMENTS = (
            "/login", "/register", "/forgot",
            "/verify", "/otp", "/2fa", "/two-factor",
            "/email-verification", "/phone-verification",
            "/trusted-device",
        )

        print("Waiting for login to complete (including 2FA if enabled)...")
        print(f"  Current page: {LOGIN_URL}\n")

        def _is_logged_in(url: str) -> bool:
            in_auth_flow = any(f in url for f in _AUTH_FLOW_FRAGMENTS)
            return "stockbit.com" in url and not in_auth_flow

        try:
            # event-driven wait — fires as soon as the URL predicate matches
            page.wait_for_url(_is_logged_in, timeout=timeout * 1_000)
            print(f"  Logged in → {page.url}")
            page.wait_for_timeout(2_000)  # let app shell settle + localStorage populate
            logged_in = True
        except Exception as e:
            if "Timeout" in str(e):
                print(f"\nTimeout reached ({timeout}s). Last URL: {page.url}")
            else:
                print(f"\nLogin detection error: {e}")

        if logged_in:
            # Wait for the app to finish persisting credentials to the profile
            # (IndexedDB writes are async — 2s is not always enough).
            page.wait_for_timeout(3_000)

        # Close the headed browser BEFORE writing the marker or doing anything else.
        # Opening a second browser on the same profile dir while this one is still
        # running causes Chromium to corrupt or reset the credential storage.
        ctx.close()

        if logged_in:
            profile_dir.mkdir(parents=True, exist_ok=True)
            marker = profile_dir / ".logged_in_at"
            marker.write_text(str(time.time()))
            print(
                f"\nSession saved → {profile_dir}/\n"
                f"  The browser profile stores all cookies and tokens.\n"
                f"  It will stay logged in across runs (like a Chrome profile)."
            )
            print("Run 'saham fetch stockbit status' to verify.")
            print("Run 'saham fetch stockbit spy' to discover API endpoints.")
        else:
            print("\nTimeout — login not detected. Session NOT saved.")
            print("Run 'saham fetch stockbit login' again and complete login within the time limit.")


def get_session_status(
    session_file: Path = DEFAULT_SESSION_FILE,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
) -> dict:
    """Return info about the saved session without opening a browser."""
    marker = profile_dir / ".logged_in_at"

    # Prefer persistent profile
    if profile_dir.exists() and any(profile_dir.iterdir()):
        age_hours: float | None = None
        if marker.exists():
            try:
                age_hours = round((time.time() - float(marker.read_text())) / 3600, 1)
            except Exception:
                pass
        # Stockbit API tokens typically expire within 8–12 hours.
        # Flag sessions older than 8h as needing re-login.
        likely_valid = age_hours is None or age_hours < 8
        return {
            "exists": True,
            "type": "persistent_profile",
            "path": str(profile_dir),
            "age_hours": age_hours,
            "likely_valid": likely_valid,
        }

    # Fall back to legacy cookie file
    if not session_file.exists():
        return {"exists": False, "path": str(session_file), "type": "none"}

    with open(session_file) as f:
        data = json.load(f)

    cookies = data.get("cookies", [])
    local_storage = data.get("local_storage", {})
    saved_at = data.get("saved_at")

    age_hours = None
    if saved_at:
        try:
            age_hours = round((time.time() - float(saved_at)) / 3600, 1)
        except Exception:
            pass

    auth_cookies = [c for c in cookies if any(
        kw in c.get("name", "").lower()
        for kw in ("session", "token", "auth", "jwt", "sid", "user")
    )]
    auth_ls_keys = [k for k in local_storage if any(
        kw in k.lower() for kw in ("token", "auth", "jwt", "user", "session", "access")
    )]

    return {
        "exists": True,
        "type": "cookie_file",
        "path": str(session_file),
        "cookie_count": len(cookies),
        "auth_cookie_count": len(auth_cookies),
        "local_storage_keys": len(local_storage),
        "auth_local_storage_keys": auth_ls_keys[:5],
        "age_hours": age_hours,
        "likely_valid": len(auth_ls_keys) > 0 or len(auth_cookies) > 0,
    }
