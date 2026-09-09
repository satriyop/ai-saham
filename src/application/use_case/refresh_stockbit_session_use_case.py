"""Refresh Stockbit auth and fail closed unless status shows a usable RS256 JWT.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.stockbit_auth import (
    StockbitAuthFailure,
    StockbitAuthFailureKind,
    StockbitAuthPort,
    StockbitAuthReady,
    StockbitAuthRefreshMode,
)
from src.application.services.stockbit_session import (
    StockbitSessionStatus,
    status_shows_usable_rs256,
)


@dataclass(frozen=True)
class RefreshStockbitSessionRequest:
    mode: StockbitAuthRefreshMode


@dataclass(frozen=True)
class RefreshStockbitSessionResult:
    """Outcome of an explicit reauth. Ready only when inspect() is usable RS256."""

    ready: bool
    status: StockbitSessionStatus
    failure: StockbitAuthFailure | None = None


def _failure_for_unusable_status(status: StockbitSessionStatus) -> StockbitAuthFailure:
    if not status.profile_exists:
        kind = StockbitAuthFailureKind.MISSING_PROFILE
    elif not status.token_exists or status.token_state == "missing":
        kind = StockbitAuthFailureKind.MISSING_TOKEN
    elif status.token_state == "expired":
        kind = StockbitAuthFailureKind.EXPIRED
    elif status.token_state == "invalid":
        kind = StockbitAuthFailureKind.INVALID_TOKEN
    else:
        kind = StockbitAuthFailureKind.REFRESH_FAILED
    return StockbitAuthFailure(
        kind=kind,
        message=(
            "Reauth did not leave a usable RS256 JWT "
            f"(status token_state={status.token_state}). "
            "`saham fetch stockbit status` must show a usable RS256 JWT."
        ),
    )


class RefreshStockbitSessionUseCase:
    """Explicit reauth. Success requires the same usable JWT that status shows."""

    def __init__(self, auth: StockbitAuthPort) -> None:
        self._auth = auth

    def execute(self, request: RefreshStockbitSessionRequest) -> RefreshStockbitSessionResult:
        outcome = self._auth.force_refresh(request.mode)
        status = self._auth.inspect()
        if isinstance(outcome, StockbitAuthFailure):
            return RefreshStockbitSessionResult(
                ready=False,
                status=status,
                failure=outcome,
            )
        if not isinstance(outcome, StockbitAuthReady) or not status_shows_usable_rs256(status):
            return RefreshStockbitSessionResult(
                ready=False,
                status=status,
                failure=_failure_for_unusable_status(status),
            )
        return RefreshStockbitSessionResult(ready=True, status=status)
