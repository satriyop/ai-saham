"""
Stockbit Exodus Bearer token interception and extraction.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.infrastructure.browser.stockbit_browser_context import (
    ORDERBOOK_PAGE_URL,
    _persistent_context,
    _require_playwright,
    default_stockbit_profile_dir,
)
from src.infrastructure.config.stockbit_config import (
    StockbitConfig,
    load_stockbit_config,
)

logger = logging.getLogger(__name__)


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


def extract_exodus_token(
    profile_dir: Path | None = None,
    headless: bool = True,
    timeout: int | None = None,
    *,
    stockbit_config: StockbitConfig | None = None,
) -> str | None:
    """
    Open a (headless) browser with the saved profile, navigate to trigger an
    authenticated Exodus request, and return the intercepted RS256 Bearer token.

    Used by StockbitApiClient as the token_refresher callable. Returns None if
    the profile is missing or the session has expired (needs re-login).
    """
    profile_dir = profile_dir or default_stockbit_profile_dir()
    cfg = stockbit_config or load_stockbit_config()
    nav_timeout = timeout or cfg.nav_timeout_ms
    settle_ms = cfg.spa_settle_ms

    if not (profile_dir.exists() and any(profile_dir.iterdir())):
        logger.debug("No Stockbit profile at %s — run: saham fetch stockbit login", profile_dir)
        return None

    sync_playwright = _require_playwright()
    try:
        with sync_playwright() as pw:
            ctx, page = _persistent_context(pw, profile_dir, headless=headless)
            token_box = _intercept_token(page)
            try:
                page.goto(ORDERBOOK_PAGE_URL, timeout=nav_timeout, wait_until="domcontentloaded")
                page.wait_for_timeout(settle_ms)
            except Exception as e:
                logger.debug("Navigation failed during token extraction: %s", e)
            token = _resolve_token(page, token_box)
            ctx.close()
            return token
    except Exception as e:
        logger.debug("Token extraction failed: %s", e)
        return None
