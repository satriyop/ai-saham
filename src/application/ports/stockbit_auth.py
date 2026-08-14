"""Stockbit auth recovery port — typed Ready | AuthFailure, no JWT on the interface.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from src.application.services.stockbit_session import StockbitSessionStatus


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
