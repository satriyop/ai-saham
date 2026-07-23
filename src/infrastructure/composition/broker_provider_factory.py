"""Broker data provider construction for non-CLI composition roots.

Selects between the Stockbit and IDX broker data provider implementations by an
explicit name or Stockbit-session auto-detection. This is infrastructure
wiring — choosing which concrete provider to construct — not fetch/cache policy.

It exists so composition roots outside the CLI adapter (for example the TUI)
can build a live broker provider without importing a CLI module.

Layer: Infrastructure (composition)
"""

from __future__ import annotations

from src.infrastructure.data_providers.idx import IdxBrokerDataProvider


def create_broker_provider(name: str | None = None) -> tuple[object, str]:
    """Create a broker provider by explicit name, or auto-detect if ``None``.

    Auto-detect order:
      1. Authenticated Stockbit session (preferred).
      2. IDX public API (always-available fallback).

    Returns ``(provider, provider_name)``.
    """
    from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider
    from src.infrastructure.browser.stockbit_config_bundle import (
        load_stockbit_provider_config,
    )
    from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session

    if name == "idx":
        return IdxBrokerDataProvider(), "idx"
    if name is not None and name != "stockbit":
        raise ValueError(f"Unknown broker provider: {name}. Choose from: idx, stockbit")

    stockbit_config = load_stockbit_provider_config()
    session = get_stockbit_session(stockbit_config)
    if session and session.authenticated:
        provider = StockbitBrokerProvider(session.api_client, stockbit_config=stockbit_config)
        return provider, "stockbit"
    return IdxBrokerDataProvider(), "idx"
