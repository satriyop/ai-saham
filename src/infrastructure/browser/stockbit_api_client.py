"""
StockbitApiClient — authenticated HTTP client for the Exodus API.

Reads the persisted JWT from StockbitTokenStore before each request.
On 401, triggers a single token refresh (via injected token_refresher)
and retries. If the refresh also fails, returns None.

The token_refresher callable is injected so this module never hard-imports
playwright — the app still runs without Playwright installed as long as a
valid persisted token exists.

Layer: Infrastructure
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore

logger = logging.getLogger(__name__)

_BROWSER_COMPATIBLE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_EXODUS_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,id;q=0.8",
    "user-agent": _BROWSER_COMPATIBLE_USER_AGENT,
    "x-platform": "web",
    "origin": "https://stockbit.com",
    "referer": "https://stockbit.com/",
}


class StockbitSessionExpired(RuntimeError):
    """Raised when the Exodus API rejects our token with 401 even after refresh."""


class StockbitApiClient:
    """
    Thin authenticated HTTP client for exodus.stockbit.com.

    Args:
        token_store: Persistent JWT storage.
        token_refresher: Callable that launches the browser to extract a fresh
            RS256 Bearer token. Returns the token string or None on failure.
            Injected to keep playwright as an optional dependency.
    """

    def __init__(
        self,
        token_store: StockbitTokenStore,
        token_refresher: Callable[[], str | None],
    ) -> None:
        self._store = token_store
        self._refresher = token_refresher

    def get(self, url: str, params: dict | None = None) -> dict | None:
        """
        GET url with Bearer auth. Refreshes token once on 401, then retries.
        Returns parsed JSON dict, or None on unrecoverable failure.

        At most ONE browser launch per call: if the token was already refreshed
        (because the store was empty), a subsequent 401 is treated as terminal.
        """
        token = self._store.load()
        already_refreshed = False

        if token is None:
            token = self._do_refresh()
            already_refreshed = True
            if token is None:
                return None

        try:
            return self._http_get(url, token, params)
        except _NeedsTokenRefresh:
            if already_refreshed:
                logger.warning("Stockbit 401 after token refresh — session unusable: %s", url)
                return None

        token = self._do_refresh()
        if token is None:
            return None
        try:
            return self._http_get(url, token, params)
        except _NeedsTokenRefresh:
            logger.warning("Stockbit 401 after token refresh — session unusable: %s", url)
            return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _do_refresh(self) -> str | None:
        logger.debug("Extracting fresh Stockbit token via browser")
        token = self._refresher()
        if not token:
            logger.warning("Token refresh returned None — is the browser profile logged in?")
            return None

        candidate = self._store.describe_candidate(token)
        if candidate.state != "valid" or candidate.algorithm != "RS256":
            logger.warning("Token refresh did not return a usable RS256 Exodus JWT")
            return None

        self._store.save(token)
        logger.debug("Token persisted (%d chars)", len(token))
        return token

    def _http_get(self, url: str, token: str, params: dict | None) -> dict | None:
        import httpx

        headers = {**_EXODUS_HEADERS, "Authorization": f"Bearer {token}"}
        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=15)
            if resp.status_code == 401:
                raise _NeedsTokenRefresh
            resp.raise_for_status()
            return resp.json()
        except _NeedsTokenRefresh:
            raise
        except Exception as e:
            logger.debug("Exodus GET failed: %s — %s", url, e)
            return None


class _NeedsTokenRefresh(Exception):
    """Internal sentinel — 401 received, caller should refresh token."""


# ── Factory ────────────────────────────────────────────────────────────────


def create_stockbit_api_client(
    profile_dir: Path | None = None,
    headless: bool = True,
    timeout: int | None = None,
) -> StockbitApiClient:
    """
    Build a StockbitApiClient backed by the default persistent profile.

    Lazily imports playwright only when a token refresh is actually needed.
    Call once per CLI invocation and share the instance across all providers.
    """
    from src.infrastructure.browser.stockbit_browser_context import (
        DEFAULT_PROFILE_DIR,
    )
    from src.infrastructure.browser.stockbit_token_extractor import (
        extract_exodus_token,
    )
    from src.infrastructure.config.stockbit_config import load_stockbit_config

    resolved_dir = profile_dir or DEFAULT_PROFILE_DIR
    cfg = load_stockbit_config()
    resolved_timeout = timeout or cfg.nav_timeout_ms
    token_store = StockbitTokenStore(resolved_dir / "token.json")

    def _refresher() -> str | None:
        return extract_exodus_token(resolved_dir, headless=headless, timeout=resolved_timeout)

    return StockbitApiClient(token_store, _refresher)
