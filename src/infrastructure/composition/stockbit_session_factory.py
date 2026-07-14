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

from src.application.services.stockbit_session import StockbitSession
from src.infrastructure.browser.stockbit_api_client import create_stockbit_api_client
from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider
from src.infrastructure.browser.stockbit_browser_context import default_stockbit_profile_dir
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.config.stockbit_config import StockbitConfig


def get_stockbit_session(stockbit_config: StockbitConfig | None = None) -> StockbitSession | None:
    """Return a StockbitSession if a valid Stockbit profile exists, else None.

    Loads `StockbitConfig` once (unless the caller already has one to share)
    and passes it explicitly into the api client and broker provider it builds.

    Never raises. Returns None when:
    - .stockbit_profile/ directory is absent
    - any unexpected exception during construction or auth check
    """
    try:
        if not default_stockbit_profile_dir().exists():
            return None
        cfg = stockbit_config or load_stockbit_provider_config()
        api_client = create_stockbit_api_client(stockbit_config=cfg)
        authenticated = StockbitBrokerProvider(api_client, stockbit_config=cfg).is_authenticated()
        return StockbitSession(api_client=api_client, authenticated=authenticated)
    except Exception:
        return None
