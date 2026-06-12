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
from src.domain.value_objects.screener_result import MoverData, OrderBookBid

logger = logging.getLogger(__name__)

DEFAULT_SESSION_FILE = Path("stockbit_session.json")

# ── Stockbit URLs ──────────────────────────────────────────────────────────
BASE_URL = "https://stockbit.com"
SCREENER_URL = "https://stockbit.com/screener"
ORDER_BOOK_URL = "https://stockbit.com/stock/{ticker}/orderbook"
LOGIN_URL = "https://stockbit.com/login"
EXODUS_API = "https://exodus.stockbit.com"

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
        headless: bool = True,
        timeout: int = NAV_TIMEOUT,
        api_patterns_file: Path | None = None,
    ) -> None:
        self._session_file = session_file
        self._headless = headless
        self._timeout = timeout
        # Optional: load custom API patterns discovered by `saham stockbit spy`
        self._api_patterns = _load_api_patterns(api_patterns_file) if api_patterns_file else {}

    def fetch_preopen_movers(self, iev_min: int) -> list[MoverData]:
        """Navigate screener page; extract movers via API intercept or DOM."""
        sync_playwright = _require_playwright()
        session = _load_session(self._session_file)

        with sync_playwright() as pw:
            browser, ctx, page = _new_authenticated_context(
                pw, session, headless=self._headless
            )

            captured_responses: list[dict] = []

            def on_response(response):
                if response.status != 200:
                    return
                ct = response.headers.get("content-type", "")
                if "json" not in ct:
                    return
                if _url_matches(response.url, _MOVERS_URL_PATTERNS):
                    try:
                        captured_responses.append({
                            "url": response.url,
                            "body": response.json(),
                        })
                        logger.info("Captured movers API: %s", response.url)
                    except Exception as e:
                        logger.debug("Failed to parse response from %s: %s", response.url, e)

            page.on("response", on_response)

            try:
                page.goto(SCREENER_URL, timeout=self._timeout)
                page.wait_for_load_state("networkidle", timeout=self._timeout)
                page.wait_for_timeout(SPA_SETTLE_MS)

                # Try API intercept first
                if captured_responses:
                    movers = _parse_movers_from_api(captured_responses, iev_min)
                    if movers:
                        logger.info("API intercept: %d movers found", len(movers))
                        return movers
                    logger.warning("API intercept: response captured but could not parse movers")

                # Fallback: DOM scraping
                logger.info("Falling back to DOM scraping for movers")
                movers = _scrape_movers_from_dom(page, iev_min)
                return movers

            finally:
                browser.close()

    def fetch_order_book_best_bid(self, ticker: str) -> OrderBookBid | None:
        """Navigate order book page; extract best bid via API intercept or DOM."""
        sync_playwright = _require_playwright()
        session = _load_session(self._session_file)
        url = ORDER_BOOK_URL.format(ticker=ticker.upper())

        with sync_playwright() as pw:
            browser, ctx, page = _new_authenticated_context(
                pw, session, headless=self._headless
            )

            captured_responses: list[dict] = []

            def on_response(response):
                if response.status != 200:
                    return
                ct = response.headers.get("content-type", "")
                if "json" not in ct:
                    return
                if _url_matches(response.url, _ORDERBOOK_URL_PATTERNS):
                    try:
                        captured_responses.append({
                            "url": response.url,
                            "body": response.json(),
                        })
                        logger.info("Captured orderbook API: %s", response.url)
                    except Exception as e:
                        logger.debug("Failed to parse %s: %s", response.url, e)

            page.on("response", on_response)

            try:
                page.goto(url, timeout=self._timeout)
                page.wait_for_load_state("networkidle", timeout=self._timeout)
                page.wait_for_timeout(SPA_SETTLE_MS)

                if captured_responses:
                    bid = _parse_best_bid_from_api(captured_responses, ticker)
                    if bid:
                        logger.info("API intercept: best bid %s = %s", ticker, bid.price)
                        return bid
                    logger.warning("API intercept: response captured but could not parse bid")

                logger.info("Falling back to DOM scraping for order book")
                return _scrape_best_bid_from_dom(page, ticker)

            finally:
                browser.close()


# ── API response parsers ────────────────────────────────────────────────────
# These need updating once `saham stockbit spy` reveals the real response shape.
# Currently structured to try common patterns and log what it finds.

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
    for key in ("volume", "lot", "lots", "qty", "quantity", "vol", "v"):
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

    session = _load_session(session_file)
    captured: list[dict] = []

    with sync_playwright() as pw:
        browser, ctx, page = _new_authenticated_context(
            pw, session, headless=False
        )

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
            page.goto(url, timeout=NAV_TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
            page.wait_for_timeout(settle_ms)
        except KeyboardInterrupt:
            pass
        finally:
            browser.close()

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
    timeout: int = 300,
) -> None:
    """
    Launch headed Chromium for manual Stockbit login. Saves cookies on success.

    Args:
        session_file: Where to write session cookies JSON
        timeout: Seconds to wait for login completion
    """
    sync_playwright = _require_playwright()

    print("Opening Stockbit login page in a browser window.")
    print(f"Please log in manually. You have {timeout} seconds.")
    if timeout < 180:
        print("Tip: use --timeout 300 if you have 2FA enabled.")
    print(f"Session will be saved to: {session_file}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        # domcontentloaded avoids hanging on SPA navigation
        page.goto(LOGIN_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")

        logged_in = False

        # Pages that are part of the auth flow — keep waiting while on any of these
        _AUTH_FLOW_FRAGMENTS = (
            "/login", "/register", "/forgot",
            "/verify", "/otp", "/2fa", "/two-factor",
            "/email-verification", "/phone-verification",
        )

        print("Waiting for login to complete (including 2FA if enabled)...")
        print("Current URL will be printed every 5 seconds.\n")

        last_printed_url = ""
        try:
            start = time.time()
            while time.time() - start < timeout:
                try:
                    current_url = page.url

                    if current_url != last_printed_url:
                        elapsed = int(time.time() - start)
                        print(f"  [{elapsed}s] {current_url}")
                        last_printed_url = current_url

                    in_auth_flow = any(f in current_url for f in _AUTH_FLOW_FRAGMENTS)
                    on_stockbit = "stockbit.com" in current_url

                    # Logged in = on stockbit.com, not on any auth/login page
                    if on_stockbit and not in_auth_flow and current_url != LOGIN_URL:
                        page.wait_for_timeout(2_000)  # let app shell settle
                        logged_in = True
                        break
                except Exception:
                    pass
                time.sleep(1)
        except KeyboardInterrupt:
            pass

        if logged_in:
            cookies = ctx.cookies()

            # Capture localStorage — Stockbit stores JWT/auth tokens here, not in cookies
            local_storage: dict = {}
            session_storage: dict = {}
            try:
                local_storage = page.evaluate("() => ({...localStorage})")
            except Exception:
                pass
            try:
                session_storage = page.evaluate("() => ({...sessionStorage})")
            except Exception:
                pass

            session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(session_file, "w") as f:
                json.dump(
                    {
                        "cookies": cookies,
                        "local_storage": local_storage,
                        "session_storage": session_storage,
                        "saved_at": str(time.time()),
                    },
                    f,
                    indent=2,
                )
            auth_keys = [k for k in local_storage if any(
                kw in k.lower() for kw in ("token", "auth", "jwt", "user", "session")
            )]
            print(
                f"\nSession saved → {session_file}\n"
                f"  Cookies     : {len(cookies)}\n"
                f"  localStorage: {len(local_storage)} keys"
                + (f" (auth keys: {', '.join(auth_keys[:5])})" if auth_keys else "")
            )
            print("Run 'saham stockbit status' to verify.")
            print("Run 'saham stockbit spy' to discover API endpoints.")
        else:
            print("\nTimeout — login not detected. Session NOT saved.")
            print("Run 'saham stockbit login' again and complete login within the time limit.")

        browser.close()


def get_session_status(session_file: Path = DEFAULT_SESSION_FILE) -> dict:
    """Return info about the saved session without opening a browser."""
    if not session_file.exists():
        return {"exists": False, "path": str(session_file)}

    with open(session_file) as f:
        data = json.load(f)

    cookies = data.get("cookies", [])
    local_storage = data.get("local_storage", {})
    saved_at = data.get("saved_at")

    age_hours: float | None = None
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

    # Valid session = has localStorage auth tokens (Stockbit stores JWT there)
    likely_valid = len(auth_ls_keys) > 0 or len(auth_cookies) > 0

    return {
        "exists": True,
        "path": str(session_file),
        "cookie_count": len(cookies),
        "auth_cookie_count": len(auth_cookies),
        "local_storage_keys": len(local_storage),
        "auth_local_storage_keys": auth_ls_keys[:5],
        "age_hours": age_hours,
        "likely_valid": likely_valid,
    }
