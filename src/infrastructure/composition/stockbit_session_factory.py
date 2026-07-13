"""
Stockbit session construction (infrastructure composition root).

Consolidates the repeated try/except/auth-check pattern that was duplicated
across multiple CLI adapters. Adapters call get_stockbit_session() once and
receive a StockbitSession with the api_client already wired. This is
concrete wiring (profile-dir check, api_client construction, auth check), so
it lives in infrastructure, not application. The StockbitSession/
StockbitSessionStatus DTOs stay in
src.application.services.stockbit_session since they carry no infrastructure
dependency and are consumed by application/adapter code alike.

Layer: Infrastructure (composition root)
"""

from __future__ import annotations

from pathlib import Path

from src.application.services.stockbit_session import StockbitSession
from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider
from src.infrastructure.config.app_config import APP_CFG


def get_stockbit_session() -> StockbitSession | None:
    """Return a StockbitSession if a valid Stockbit profile exists, else None.

    Never raises. Returns None when:
    - .stockbit_profile/ directory is absent
    - any unexpected exception during construction or auth check
    """
    try:
        if not Path(APP_CFG.storage.stockbit_profile_dir).exists():
            return None
        api_client = create_stockbit_api_client()
        authenticated = StockbitBrokerProvider(api_client).is_authenticated()
        return StockbitSession(api_client=api_client, authenticated=authenticated)
    except Exception:
        return None
