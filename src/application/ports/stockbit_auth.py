"""Stockbit auth recovery port — typed Ready | AuthFailure, no JWT on the interface.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from src.application.services.stockbit_session import StockbitSessionStatus

# Evening JWT watch treats remaining at or below this window as needing a newer
# token before the next morning desk. Headless capture of the same near-expiry
# RS256 must not report success.
HEADLESS_JWT_SHORT_REMAINING_SECONDS = 36 * 3600


class StockbitAuthRefreshMode(str, Enum):
    """Refresh strategy. Headless is cron-safe; headed is interactive recovery."""

    HEADLESS = "headless"
    HEADED = "headed"


class StockbitAuthFailureKind(str, Enum):
    """Stable AuthFailure kinds for adapters and CLI mapping."""

    MISSING_PROFILE = "missing_profile"
    MISSING_TOKEN = "missing_token"
    INVALID_TOKEN = "invalid_token"
    EXPIRED = "expired"
    REFRESH_FAILED = "refresh_failed"
    AUTH_UI = "auth_ui"


@dataclass(frozen=True)
class StockbitAuthReady:
    """Ensure/refresh succeeded. Never carries a JWT."""


@dataclass(frozen=True)
class StockbitAuthFailure:
    """Ensure/refresh failed. Message must not contain JWT or password material."""

    kind: StockbitAuthFailureKind
    message: str


StockbitAuthOutcome = StockbitAuthReady | StockbitAuthFailure


def ready_requires_usable_status(
    outcome: StockbitAuthOutcome,
    status: StockbitSessionStatus,
) -> StockbitAuthOutcome:
    """Ready only if inspect() would show token_state=valid (local JWT health)."""
    if isinstance(outcome, StockbitAuthFailure):
        return outcome
    if status.token_state == "valid":
        return outcome
    if status.token_state == "expired":
        return StockbitAuthFailure(
            kind=StockbitAuthFailureKind.EXPIRED,
            message="Refresh did not leave a usable RS256 JWT (token expired).",
        )
    return StockbitAuthFailure(
        kind=StockbitAuthFailureKind.REFRESH_FAILED,
        message=(
            f"Refresh did not leave a usable RS256 JWT (token state is {status.token_state})."
        ),
    )


def _parse_token_expires_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _token_expires_at_moved_later(before: str | None, after: str | None) -> bool:
    after_dt = _parse_token_expires_at(after)
    if after_dt is None:
        return False
    before_dt = _parse_token_expires_at(before)
    if before_dt is None:
        return True
    return after_dt > before_dt


def _remaining_minutes_label(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    return f"{seconds // 60} min"


def ready_requires_jwt_exp_advance_when_short(
    outcome: StockbitAuthOutcome,
    before: StockbitSessionStatus,
    after: StockbitSessionStatus,
) -> StockbitAuthOutcome:
    """After headless Ready + usable JWT: fail-closed if remaining is still short.

    If ``token_state`` is valid, remaining is ``<= 36h``, and ``token_expires_at``
    did not move later than the pre-refresh inspect, headless did not extend
    ``jwt_exp``. Remaining ``> 36h`` may stay Ready even when expiry is unchanged.
    """
    if isinstance(outcome, StockbitAuthFailure):
        return outcome
    if after.token_state != "valid":
        return outcome
    remaining = after.token_seconds_remaining
    if remaining is None or remaining > HEADLESS_JWT_SHORT_REMAINING_SECONDS:
        return outcome
    if _token_expires_at_moved_later(before.token_expires_at, after.token_expires_at):
        return outcome
    return StockbitAuthFailure(
        kind=StockbitAuthFailureKind.REFRESH_FAILED,
        message=(
            "Headless refresh did not extend jwt_exp "
            f"(remaining {_remaining_minutes_label(after.token_seconds_remaining)}, "
            f"was {_remaining_minutes_label(before.token_seconds_remaining)}). "
            "Headed login is required."
        ),
    )


@runtime_checkable
class StockbitAuthPort(Protocol):
    """Application-facing Stockbit auth recovery seam."""

    def ensure_usable(self) -> StockbitAuthOutcome:
        """Ready if a usable session exists (may auto headless-refresh once)."""
        ...

    def force_refresh(self, mode: StockbitAuthRefreshMode) -> StockbitAuthOutcome:
        """Explicit refresh. Headless is cron-safe; headed is interactive."""
        ...

    def inspect(self) -> StockbitSessionStatus:
        """Local session health. Never returns the JWT string."""
        ...
