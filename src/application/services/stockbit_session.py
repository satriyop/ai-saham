"""
StockbitSession — application-layer factory for the Stockbit auth state.

Consolidates the repeated try/except/auth-check pattern that was duplicated
across multiple CLI adapters. Adapters call get_stockbit_session() once and
receive a StockbitSession with the api_client already wired; no adapter
needs to own the profile-dir check, api_client construction, or auth check.

Layer: Application (infrastructure is imported lazily inside the factory)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_api_client import StockbitApiClient


@dataclass(frozen=True)
class StockbitSession:
    api_client: "StockbitApiClient"
    authenticated: bool


def get_stockbit_session() -> StockbitSession | None:
    """Return a StockbitSession if a valid Stockbit profile exists, else None.

    Never raises. Returns None when:
    - .stockbit_profile/ directory is absent
    - any unexpected exception during construction or auth check
    """
    try:
        from pathlib import Path

        from src.infrastructure.browser.playwright_stockbit_provider import StockbitBrokerProvider
        from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
        from src.infrastructure.config.app_config import APP_CFG

        if not Path(APP_CFG.storage.stockbit_profile_dir).exists():
            return None
        api_client = create_stockbit_api_client()
        authenticated = StockbitBrokerProvider(api_client).is_authenticated()
        return StockbitSession(api_client=api_client, authenticated=authenticated)
    except Exception:
        return None
