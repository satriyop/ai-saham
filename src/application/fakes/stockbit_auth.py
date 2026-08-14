"""In-memory StockbitAuthPort adapter for tests.

Layer: Application (test fake)
"""

from __future__ import annotations

from src.application.ports.stockbit_auth import (
    StockbitAuthFailure,
    StockbitAuthOutcome,
    StockbitAuthReady,
    StockbitAuthRefreshMode,
)
from src.application.services.stockbit_session import StockbitSessionStatus


def _default_status() -> StockbitSessionStatus:
    return StockbitSessionStatus(
        profile_exists=True,
        profile_path=".stockbit_profile",
        browser_login_age_hours=None,
        token_exists=False,
        token_state="missing",
        token_expires_at=None,
        token_seconds_remaining=None,
        token_expiry_source=None,
    )


class FakeStockbitAuth:
    """Configurable StockbitAuthPort with no Playwright or token store."""

    def __init__(
        self,
        *,
        ensure_result: StockbitAuthOutcome | None = None,
        refresh_results: dict[StockbitAuthRefreshMode, StockbitAuthOutcome] | None = None,
        status: StockbitSessionStatus | None = None,
    ) -> None:
        self.ensure_result: StockbitAuthOutcome = ensure_result or StockbitAuthReady()
        self.refresh_results = refresh_results or {}
        self.status = status or _default_status()
        self.ensure_calls = 0
        self.refresh_calls: list[StockbitAuthRefreshMode] = []

    def ensure_usable(self) -> StockbitAuthOutcome:
        self.ensure_calls += 1
        return self.ensure_result

    def force_refresh(self, mode: StockbitAuthRefreshMode) -> StockbitAuthOutcome:
        self.refresh_calls.append(mode)
        if mode in self.refresh_results:
            return self.refresh_results[mode]
        if isinstance(self.ensure_result, StockbitAuthFailure):
            return self.ensure_result
        return StockbitAuthReady()

    def inspect(self) -> StockbitSessionStatus:
        return self.status
