"""
StockbitSession — application-layer factory for the Stockbit auth state.

Consolidates the repeated try/except/auth-check pattern that was duplicated
across multiple CLI adapters. Adapters call get_stockbit_session() once and
receive a StockbitSession with the api_client already wired; no adapter
needs to own the profile-dir check, api_client construction, or auth check.

StockbitSessionStatus is the read-only authentication-health DTO used by
`saham fetch stockbit status` and system-status checks. Its composer function
(get_stockbit_session_status) lives in infrastructure — see
src/infrastructure/browser/playwright_stockbit_browser.py — because building
it requires reading StockbitTokenStore and the browser profile marker
directly, and application must not import infrastructure (see
tests/architecture/test_layer_boundaries.py). Infrastructure is allowed to
depend inward on this DTO's shape.

Layer: Application (infrastructure is imported lazily inside get_stockbit_session)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient


@dataclass(frozen=True)
class StockbitSession:
    api_client: "StockbitApiClient"
    authenticated: bool


@dataclass(frozen=True)
class StockbitSessionStatus:
    """Read-only authentication-health snapshot. Never carries the JWT itself.

    browser_login_age_hours is informational only — it must never be used to
    decide authorization. token_state is the locally-computed source of truth
    for whether the persisted JWT is usable; it does not prove Stockbit has
    accepted the token (only an HTTP 401/200 response can prove that).
    """

    profile_exists: bool
    profile_path: str
    browser_login_age_hours: float | None
    token_exists: bool
    token_state: Literal["valid", "expired", "missing", "invalid"]
    token_expires_at: str | None  # ISO-8601 UTC
    token_seconds_remaining: int | None
    token_expiry_source: Literal["jwt_exp", "fallback_ttl"] | None


def get_stockbit_session() -> StockbitSession | None:
    """Return a StockbitSession if a valid Stockbit profile exists, else None.

    Never raises. Returns None when:
    - .stockbit_profile/ directory is absent
    - any unexpected exception during construction or auth check
    """
    try:
        from pathlib import Path

        from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
        from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider
        from src.infrastructure.config.app_config import APP_CFG

        if not Path(APP_CFG.storage.stockbit_profile_dir).exists():
            return None
        api_client = create_stockbit_api_client()
        authenticated = StockbitBrokerProvider(api_client).is_authenticated()
        return StockbitSession(api_client=api_client, authenticated=authenticated)
    except Exception:
        return None
