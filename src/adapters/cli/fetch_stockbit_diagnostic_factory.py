"""
Factory for constructing an authenticated Stockbit provider for CLI diagnostics.

Layer: Adapter (composition root / infrastructure wiring helper)
"""

from __future__ import annotations

from src.infrastructure.browser.playwright_stockbit_provider import PlaywrightStockbitProvider
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session


def create_authenticated_stockbit_provider() -> PlaywrightStockbitProvider:
    """Return a PlaywrightStockbitProvider backed by the saved Stockbit session.

    Raises:
        ValueError: If no authenticated Stockbit session exists.
    """
    stockbit_config = load_stockbit_provider_config()
    session = get_stockbit_session(stockbit_config)
    if not session or not session.authenticated:
        raise ValueError("Stockbit session expired. Run `saham fetch stockbit login` to refresh.")
    return PlaywrightStockbitProvider(
        api_client=session.api_client, stockbit_config=stockbit_config
    )
