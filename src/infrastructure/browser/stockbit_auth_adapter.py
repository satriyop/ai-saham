"""Production StockbitAuthPort adapter: token store + reauth refresh strategies.

Layer: Infrastructure
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.ports.stockbit_auth import (
    StockbitAuthFailure,
    StockbitAuthFailureKind,
    StockbitAuthOutcome,
    StockbitAuthReady,
    StockbitAuthRefreshMode,
)
from src.application.services.stockbit_session import StockbitSessionStatus
from src.infrastructure.browser.stockbit_browser_context import default_stockbit_profile_dir
from src.infrastructure.browser.stockbit_session_actions import (
    get_stockbit_session_status,
    reauth_stockbit_session,
)
from src.infrastructure.browser.stockbit_token_store import StockbitTokenStore
from src.infrastructure.config.stockbit_config import StockbitConfig, load_stockbit_config

RefreshFn = Callable[[StockbitAuthRefreshMode], StockbitAuthOutcome]


def _profile_present(profile_dir: Path) -> bool:
    return profile_dir.exists() and any(profile_dir.iterdir())


def _map_reauth_failure(message: str) -> StockbitAuthFailure:
    lower = (message or "").lower()
    if "auth ui" in lower or "login/otp" in lower:
        kind = StockbitAuthFailureKind.AUTH_UI
    elif "no stockbit profile" in lower:
        kind = StockbitAuthFailureKind.MISSING_PROFILE
    else:
        kind = StockbitAuthFailureKind.REFRESH_FAILED
    return StockbitAuthFailure(kind=kind, message=message)


class StockbitAuthAdapter:
    """StockbitAuthPort backed by the persisted JWT store and session reauth."""

    def __init__(
        self,
        profile_dir: Path | None = None,
        token_store: StockbitTokenStore | None = None,
        *,
        refresh: RefreshFn | None = None,
        stockbit_config: StockbitConfig | None = None,
        reauth_timeout: int = 180,
    ) -> None:
        self._profile_dir = profile_dir or default_stockbit_profile_dir()
        self._store = token_store or StockbitTokenStore(self._profile_dir / "token.json")
        self._refresh = refresh
        self._cfg = stockbit_config
        self._reauth_timeout = reauth_timeout

    def ensure_usable(self) -> StockbitAuthOutcome:
        if not _profile_present(self._profile_dir):
            return StockbitAuthFailure(
                kind=StockbitAuthFailureKind.MISSING_PROFILE,
                message="No Stockbit profile. Run: saham fetch stockbit login",
            )
        if self._store.load():
            return StockbitAuthReady()
        return self.force_refresh(StockbitAuthRefreshMode.HEADLESS)

    def force_refresh(self, mode: StockbitAuthRefreshMode) -> StockbitAuthOutcome:
        if self._refresh is not None:
            return self._refresh(mode)
        return self._default_refresh(mode)

    def inspect(self) -> StockbitSessionStatus:
        return get_stockbit_session_status(self._profile_dir)

    def _default_refresh(self, mode: StockbitAuthRefreshMode) -> StockbitAuthOutcome:
        cfg = self._cfg or load_stockbit_config()
        try:
            result = reauth_stockbit_session(
                profile_dir=self._profile_dir,
                timeout=self._reauth_timeout,
                stockbit_config=cfg,
                mode=mode.value,  # type: ignore[arg-type]
            )
        except RuntimeError as exc:
            return _map_reauth_failure(str(exc))
        except Exception as exc:
            return StockbitAuthFailure(
                kind=StockbitAuthFailureKind.REFRESH_FAILED,
                message=f"Stockbit refresh failed: {exc}",
            )
        if result.success and self._store.load():
            return StockbitAuthReady()
        if result.success:
            return StockbitAuthFailure(
                kind=StockbitAuthFailureKind.REFRESH_FAILED,
                message="Reauth reported success but no usable JWT was stored.",
            )
        return _map_reauth_failure(result.message)
