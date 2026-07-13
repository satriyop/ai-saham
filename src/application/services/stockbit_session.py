"""
StockbitSession — pure application-layer DTOs for the Stockbit auth state.

StockbitSession and StockbitSessionStatus carry no infrastructure
dependency (api_client is typed as Any to avoid an infrastructure import)
and are consumed by application/adapter code alike.

The concrete session composer (get_stockbit_session) — profile-dir check,
api_client construction, auth check — lives in infrastructure. See
src/infrastructure/composition/stockbit_session_factory.py. Adapters call
that instead of this module for the session itself.

StockbitSessionStatus is the read-only authentication-health DTO used by
`saham fetch stockbit status` and system-status checks. Its composer function
(get_stockbit_session_status) lives in infrastructure — see
src/infrastructure/browser/playwright_stockbit_browser.py — because building
it requires reading StockbitTokenStore and the browser profile marker
directly, and application must not import infrastructure (see
tests/architecture/test_layer_boundaries.py). Infrastructure is allowed to
depend inward on this DTO's shape.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class StockbitSession:
    api_client: Any
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
