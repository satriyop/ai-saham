"""
Playwright-based Stockbit browser provider.

Two modes:
  1. API-intercept mode (preferred): hooks Playwright's network layer to
     capture JSON responses, bypassing fragile DOM selectors entirely.
  2. DOM-scrape mode (fallback): parses rendered HTML tables.

Flow:
  saham stockbit login   → saves browser session cookies
  saham stockbit spy     → captures all API traffic to identify endpoints
  saham stockbit test    → smoke-tests the adapter with live data
  saham intraday pre-open → uses saved session for autonomous screening

Layer: Infrastructure
Depends on: playwright (optional), BrowserDataProvider port
"""

from __future__ import annotations

import json
import logging
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.domain.ports.browser_data_provider import BrowserDataProvider
from src.domain.value_objects.screener_result import MoverData, MoverWithOrderBook, OrderBookBid

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

# ── Confirmed Exodus API endpoints (from DevTools spy, 2026-06-13) ─────────
# IEV movers: two separate board groups, mirroring how Stockbit frontend calls them.
# mover_type confirmed via DevTools: MOVER_TYPE_IEV_TOP_GAINER (NOT MOVER_CATEGORY_IEPIEV_MOVER)
_IEV_MOVER_URL_MAIN = (
    "https://exodus.stockbit.com/order-trade/market-mover"
    "?mover_type=MOVER_TYPE_IEV_TOP_GAINER"
    "&filter_stocks=FILTER_STOCKS_TYPE_MAIN_BOARD"
    "&filter_stocks=FILTER_STOCKS_TYPE_DEVELOPMENT_BOARD"
    "&filter_stocks=FILTER_STOCKS_TYPE_ACCELERATION_BOARD"
    "&filter_stocks=FILTER_STOCKS_TYPE_NEW_ECONOMY_BOARD"
)
_IEV_MOVER_URL_SPECIAL = (
    "https://exodus.stockbit.com/order-trade/market-mover"
    "?mover_type=MOVER_TYPE_IEV_TOP_GAINER"
    "&filter_stocks=FILTER_STOCKS_TYPE_SPECIAL_MONITORING_BOARD"
)
# Orderbook confirmed via DevTools: company-price-feed/v2/orderbook/companies/{TICKER}
_ORDER_BOOK_API = "https://exodus.stockbit.com/company-price-feed/v2/orderbook/companies/{ticker}"

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
            "Run: saham stockbit login"
        )
    with open(session_file) as f:
        data = json.load(f)
    if not data.get("cookies") and not data.get("local_storage"):
        raise RuntimeError(
            f"Session file '{session_file}' appears empty.\n"
            "Run: saham stockbit login to refresh."
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
                "Stockbit API session expired (401). Run: saham stockbit login"
            )
        resp.raise_for_status()
        return resp.json()
    except StockbitSessionExpired:
        raise
    except Exception as e:
        logger.warning("Exodus API call failed: %s — %s", url, e)
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
                "Run: saham stockbit login"
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
                        f"{e}\n\nRun: saham stockbit login"
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
                    raise RuntimeError(f"{e}\n\nRun: saham stockbit login") from None
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
                    ))
                    logger.info(
                        "%s: bid=%s (%s lots)  offer=%s (%s lots)",
                        mover.ticker, bid_price, bid_lots, offer_price, offer_lots,
                    )

                return results

            finally:
                ctx.close()

    def fetch_order_book_best_bid(self, ticker: str) -> OrderBookBid | None:
        """
        Fetch order book best bid from Exodus API.

        Reuses the JWT from the stream page — only navigates if no token cached.
        """
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
                page.wait_for_timeout(2_000)

                token = _resolve_token(page, token_box)
                if not token:
                    logger.warning("Could not extract JWT for order book")
                    return None

                ob_url = _ORDER_BOOK_API.format(ticker=ticker.upper())
                body = _exodus_get(ob_url, token)
                if body:
                    bid = _parse_order_book_response(body)
                    if bid:
                        logger.info("Order book: %s best bid = %s", ticker, bid.price)
                        return bid
                    logger.warning("Order book response parsed but no bid found for %s", ticker)
                    logger.debug("Response: %s", str(body)[:500])

                return None

            finally:
                ctx.close()


# ── Board-aware IEV fetcher ────────────────────────────────────────────────

def _fetch_iev_all_boards(token: str) -> list[MoverData]:
    """
    Call IEV movers API for both board groups, merge, deduplicate, sort by IEV desc.

    Mirrors how the Stockbit frontend works: two separate API calls (main boards
    and special monitoring board), then combined into one sorted list.

    Raises StockbitSessionExpired if any call returns 401.
    """
    seen: dict[str, int] = {}  # ticker → iev

    for url in (_IEV_MOVER_URL_MAIN, _IEV_MOVER_URL_SPECIAL):
        body = _exodus_get(url, token)  # raises StockbitSessionExpired on 401
        if not body:
            logger.debug("No response from %s", url)
            continue
        for mover in _parse_iev_response(body, iev_min=0):
            # Keep highest IEV if ticker appears in both boards
            if mover.iev > seen.get(mover.ticker, -1):
                seen[mover.ticker] = mover.iev

    return sorted(
        [MoverData(ticker=t, iev=v) for t, v in seen.items()],
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
            if ticker and iev is not None and iev >= iev_min:
                movers.append(MoverData(ticker=ticker, iev=iev))
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
            if ticker and iev is not None and iev >= iev_min:
                movers.append(MoverData(ticker=ticker, iev=iev))

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


def _parse_order_book_response(body: dict) -> OrderBookBid | None:
    """
    Parse order book API response from Exodus.
    Uses confirmed company-price-feed/v2/orderbook response shape.
    """
    bid_price, bid_lots, _, _ = _parse_top_of_book(body)
    if bid_price is not None and bid_lots is not None:
        return OrderBookBid(price=bid_price, volume=bid_lots)
    return None


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

    Tries common response shapes. Run `saham stockbit spy` to see the
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

    Tries common response shapes. Run `saham stockbit spy` to see the
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
    Needs calibration against actual Stockbit DOM after `saham stockbit spy`.
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
        "Run 'saham stockbit spy' to identify the correct selectors."
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
        "Run 'saham stockbit spy --url orderbook --ticker %s'",
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

    return {
        "total_responses": len(captured),
        "json_responses": len(json_responses),
        "unique_json_urls": unique_urls,
        "movers_candidates": movers_hits,
        "orderbook_candidates": orderbook_hits,
        "output_file": str(output_file),
    }


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
            # The persistent profile already saved everything to profile_dir —
            # no extraction needed. Just write a marker file so 'status' works.
            profile_dir.mkdir(parents=True, exist_ok=True)
            marker = profile_dir / ".logged_in_at"
            marker.write_text(str(time.time()))
            print(
                f"\nSession saved → {profile_dir}/\n"
                f"  The browser profile stores all cookies and tokens.\n"
                f"  It will stay logged in across runs (like a Chrome profile)."
            )

            # Warm up the API token in headless mode so the first autonomous
            # command after login doesn't hit a 401. The orderbook page reliably
            # fires Bearer-authenticated Exodus API requests on load.
            print("\nWarming up API token (headless)...", end=" ", flush=True)
            try:
                with sync_playwright() as _pw:
                    _ctx, _page = _persistent_context(_pw, profile_dir, headless=True)
                    _page.goto(ORDERBOOK_PAGE_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
                    _page.wait_for_timeout(SPA_SETTLE_MS)
                    _ctx.close()
                print("done.")
            except Exception as _e:
                print(f"skipped ({_e})")

            print("Run 'saham stockbit status' to verify.")
            print("Run 'saham stockbit spy' to discover API endpoints.")
        else:
            print("\nTimeout — login not detected. Session NOT saved.")
            print("Run 'saham stockbit login' again and complete login within the time limit.")

        ctx.close()


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
