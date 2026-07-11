"""
Playwright browser session utilities for Stockbit.

Handles: persistent profile management, JWT token extraction, authenticated
HTTP calls to the Exodus API, and the session management CLI entry points
(login, browse, spy, status).

Only persistent-profile auth is supported. Cookie-file injection was removed
because the login command always creates a persistent profile, making the
fallback unreachable in normal use.

Layer: Infrastructure
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.stockbit_config import STOCKBIT_CFG

if TYPE_CHECKING:
    from src.application.services.stockbit_session import StockbitSessionStatus

logger = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────────────────────
DEFAULT_PROFILE_DIR = Path(APP_CFG.storage.stockbit_profile_dir)

# ── Stockbit URLs ──────────────────────────────────────────────────────────
BASE_URL = "https://stockbit.com"
STREAM_URL = "https://stockbit.com/stream"
SCREENER_URL = "https://stockbit.com/screener"
ORDER_BOOK_URL = "https://stockbit.com/stock/{ticker}/orderbook"
ORDERBOOK_PAGE_URL = "https://stockbit.com/orderbook"
LOGIN_URL = "https://stockbit.com/login"
EXODUS_API = "https://exodus.stockbit.com"

# ── Timeouts ───────────────────────────────────────────────────────────────
NAV_TIMEOUT = STOCKBIT_CFG.nav_timeout_ms
ELEMENT_TIMEOUT = STOCKBIT_CFG.element_timeout_ms
SPA_SETTLE_MS = STOCKBIT_CFG.spa_settle_ms

# ── Spy target pages ───────────────────────────────────────────────────────
_STOCK_BROKER_PAGE_URL = "https://stockbit.com/broker-analysis/stock"
_BROKER_ANALYSIS_PAGE_URL = "https://stockbit.com/broker-analysis/broker"

_MOVERS_URL_PATTERNS = [
    "exodus.stockbit.com/screener",
    "exodus.stockbit.com/market/mover",
    "exodus.stockbit.com/pre-open",
    "exodus.stockbit.com/iev",
    "exodus.stockbit.com/stock/mover",
    "mover",
    "iev",
    "preopen",
]
_ORDERBOOK_URL_PATTERNS = [
    "company-price-feed/v2/orderbook",
    "exodus.stockbit.com/orderbook",
    "exodus.stockbit.com/order-book",
    "exodus.stockbit.com/stock",
    "orderbook",
    "order-book",
]
_BROKER_URL_PATTERNS = ["marketdetectors", "broker/activity", "activity/historical"]


# ── Browser helpers ────────────────────────────────────────────────────────


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


def _persistent_context(pw, profile_dir: Path, headless: bool = True):
    """
    Launch a persistent Chromium context using a saved browser profile.

    The profile directory stores ALL browser state (cookies, localStorage,
    IndexedDB, cache) exactly like a real Chrome profile.

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


def _url_matches(url: str, patterns: list[str]) -> bool:
    url_lower = url.lower()
    return any(p in url_lower for p in patterns)


def _intercept_token(page) -> list[str]:
    """
    Register a request interceptor BEFORE navigation to capture the RS256
    Bearer token Stockbit sends to exodus.stockbit.com.

    Returns a mutable list populated as requests fire.
    Call _resolve_token() after the page settles.
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

    The app uses two JWTs: an HS256 token in localStorage (in-app use) and
    an RS256 Bearer token sent to the Exodus API. Only the latter works for
    direct httpx calls, so we capture it from request headers.
    """
    captured: list[str] = []

    def _on_req(request):
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer ") and "exodus.stockbit.com" in request.url:
            captured.append(auth.removeprefix("Bearer "))

    try:
        page.on("request", _on_req)
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


# ── Session management ─────────────────────────────────────────────────────


def save_stockbit_session(
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    timeout: int = 300,
) -> None:
    """
    Launch headed Chromium for manual Stockbit login.

    Uses a persistent browser profile (.stockbit_profile/) so all browser
    state (cookies, localStorage, IndexedDB) is preserved across runs.
    The browser stays logged in exactly like a regular Chrome profile.

    Args:
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
        # Register before navigation so any Exodus Bearer token sent during or
        # after login is captured — never inferred from URL/page content.
        token_box = _intercept_token(page)
        page.goto(LOGIN_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")

        logged_in = False

        _AUTH_FLOW_FRAGMENTS = (
            "/login",
            "/register",
            "/forgot",
            "/verify",
            "/otp",
            "/2fa",
            "/two-factor",
            "/email-verification",
            "/phone-verification",
            "/trusted-device",
        )

        print("Waiting for login to complete (including 2FA if enabled)...")
        print(f"  Current page: {LOGIN_URL}\n")

        def _is_logged_in(url: str) -> bool:
            in_auth_flow = any(f in url for f in _AUTH_FLOW_FRAGMENTS)
            return "stockbit.com" in url and not in_auth_flow

        try:
            page.wait_for_url(_is_logged_in, timeout=timeout * 1_000)
            print(f"  Logged in → {page.url}")
            page.wait_for_timeout(2_000)
            logged_in = True
        except Exception as e:
            if "Timeout" in str(e):
                print(f"\nTimeout reached ({timeout}s). Last URL: {page.url}")
            else:
                print(f"\nLogin detection error: {e}")

        token: str | None = None
        if logged_in:
            page.wait_for_timeout(3_000)
            try:
                page.goto(ORDERBOOK_PAGE_URL, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
                page.wait_for_timeout(SPA_SETTLE_MS)
            except Exception as e:
                logger.debug("Post-login navigation for JWT capture failed: %s", e)
            token = _resolve_token(page, token_box)

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

            token_saved = False
            if token:
                token_store = StockbitTokenStore(profile_dir / "token.json")
                candidate = token_store.describe_candidate(token)
                if candidate.state == "valid" and candidate.algorithm == "RS256":
                    token_store.save(token)
                    token_saved = True
            if token_saved:
                print("  Exodus API JWT captured and saved.")
            else:
                print(
                    "  Warning: could not capture a usable Exodus API JWT from this login.\n"
                    "  The browser profile is saved; the token will be refreshed"
                    " automatically on the next API call."
                )
            print("Run 'saham fetch stockbit status' to verify.")
            print("Run 'saham fetch stockbit spy' to discover API endpoints.")
        else:
            print("\nTimeout — login not detected. Session NOT saved.")
            print(
                "Run 'saham fetch stockbit login' again and complete login within the time limit."
            )


def _persist_newer_token(
    token_store: StockbitTokenStore, token_box: list[str], last_seen: int
) -> int:
    """
    Opportunistically persist a newly captured Exodus token.

    If token_box has grown since last_seen, evaluate the newest captured
    token and persist it only when StockbitTokenStore.is_worth_saving()
    accepts it (locally valid RS256 JWT, newer than what's stored). Returns
    the updated last_seen index so identical/rejected tokens are not
    re-evaluated on every loop tick.
    """
    if len(token_box) <= last_seen:
        return last_seen
    candidate = token_box[-1]
    if token_store.is_worth_saving(candidate):
        token_store.save(candidate)
        logger.info("Captured newer Stockbit Exodus token during browse — saved")
    return len(token_box)


def browse_stockbit_session(
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    url: str = STREAM_URL,
) -> None:
    """
    Open a headed browser with the saved Stockbit session and keep it open.

    If no session exists or the persisted JWT is expired/missing, the login
    flow (save_stockbit_session) runs first so the user never has to manually
    re-authenticate before browsing.

    While open, any newer Exodus Bearer token observed on normal browser
    requests is opportunistically saved (see _persist_newer_token). Page
    navigation alone is never treated as authentication proof.

    Args:
        profile_dir: Persistent browser profile directory
        url: Stockbit page to open (default: stream/home)
    """
    status = get_stockbit_session_status(profile_dir)
    if not status.profile_exists or status.token_state != "valid":
        if not status.profile_exists:
            print("No Stockbit browser profile found.")
        else:
            print(f"Stockbit token state: {status.token_state}.")
        print("Running login flow to renew authentication...\n")
        save_stockbit_session(profile_dir=profile_dir)
        print("\nLogin complete. Opening browser...\n")

    sync_playwright = _require_playwright()
    token_store = StockbitTokenStore(profile_dir / "token.json")
    print(f"Using persistent profile: {profile_dir}/")
    print(f"Opening {url}")
    print("The browser will stay open until you press Ctrl+C.\n")

    with sync_playwright() as pw:
        ctx, page = _persistent_context(pw, profile_dir, headless=False)
        token_box = _intercept_token(page)
        page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")

        last_seen = 0
        try:
            while True:
                page.wait_for_timeout(10_000)
                last_seen = _persist_newer_token(token_store, token_box, last_seen)
        except KeyboardInterrupt:
            print("\nClosing browser...")
        finally:
            _persist_newer_token(token_store, token_box, last_seen)
            ctx.close()


def spy_stockbit_session(
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
        profile_dir: Persistent browser profile directory
        target: 'screener', 'orderbook', 'stock', 'stock-profile', 'broker-scan'
        ticker: Ticker to use for orderbook/stock target
        output_file: Where to save captured requests
        settle_ms: Milliseconds to wait for SPA to settle

    Returns:
        Summary dict with total_responses, unique_urls, output_file path
    """
    if not (profile_dir.exists() and any(profile_dir.iterdir())):
        raise RuntimeError("No Stockbit profile found.\nRun: saham fetch stockbit login")

    sync_playwright = _require_playwright()

    if target == "orderbook":
        url = ORDER_BOOK_URL.format(ticker=ticker.upper())
    elif target == "stock":
        url = _STOCK_BROKER_PAGE_URL
    elif target == "stock-profile":
        url = f"https://stockbit.com/stocks/{ticker.upper()}"
    elif target == "broker-scan":
        url = _BROKER_ANALYSIS_PAGE_URL
    elif target == "broker":
        url = _STOCK_BROKER_PAGE_URL
    else:
        url = SCREENER_URL

    captured: list[dict] = []

    with sync_playwright() as pw:
        ctx, page = _persistent_context(pw, profile_dir, headless=False)

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
            page.wait_for_timeout(settle_ms)
        except KeyboardInterrupt:
            pass
        finally:
            ctx.close()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(captured, f, indent=2, default=str)

    json_responses = [c for c in captured if "json" in c.get("content_type", "")]
    unique_urls = sorted(set(c["url"] for c in json_responses))

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


def extract_exodus_token(
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    headless: bool = True,
    timeout: int = NAV_TIMEOUT,
) -> str | None:
    """
    Open a (headless) browser with the saved profile, navigate to trigger an
    authenticated Exodus request, and return the intercepted RS256 Bearer token.

    Used by StockbitApiClient as the token_refresher callable. Returns None if
    the profile is missing or the session has expired (needs re-login).
    """
    if not (profile_dir.exists() and any(profile_dir.iterdir())):
        logger.debug("No Stockbit profile at %s — run: saham fetch stockbit login", profile_dir)
        return None

    sync_playwright = _require_playwright()
    try:
        with sync_playwright() as pw:
            ctx, page = _persistent_context(pw, profile_dir, headless=headless)
            token_box = _intercept_token(page)
            try:
                page.goto(ORDERBOOK_PAGE_URL, timeout=timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(SPA_SETTLE_MS)
            except Exception as e:
                logger.debug("Navigation failed during token extraction: %s", e)
            token = _resolve_token(page, token_box)
            ctx.close()
            return token
    except Exception as e:
        logger.debug("Token extraction failed: %s", e)
        return None


def get_stockbit_session_status(profile_dir: Path = DEFAULT_PROFILE_DIR) -> StockbitSessionStatus:
    """
    Compose a read-only Stockbit authentication-health snapshot.

    Never opens a browser or makes a network call. Reads two independent
    facts — the browser-profile login marker (informational age only) and
    the persisted JWT's local validity via StockbitTokenStore — and reports
    them separately rather than collapsing them into a single pass/fail
    signal. Returns the application-layer StockbitSessionStatus DTO;
    infrastructure is allowed to depend inward on that shape.
    """
    from src.application.services.stockbit_session import StockbitSessionStatus

    profile_exists = profile_dir.exists() and any(profile_dir.iterdir())

    browser_login_age_hours: float | None = None
    marker = profile_dir / ".logged_in_at"
    if marker.exists():
        try:
            browser_login_age_hours = round((time.time() - float(marker.read_text())) / 3600, 2)
        except Exception:
            browser_login_age_hours = None

    token_meta = StockbitTokenStore(profile_dir / "token.json").inspect()

    return StockbitSessionStatus(
        profile_exists=profile_exists,
        profile_path=str(profile_dir),
        browser_login_age_hours=browser_login_age_hours,
        token_exists=token_meta.exists,
        token_state=token_meta.state,
        token_expires_at=token_meta.expires_at.isoformat() if token_meta.expires_at else None,
        token_seconds_remaining=token_meta.seconds_remaining,
        token_expiry_source=token_meta.expiry_source,
    )
