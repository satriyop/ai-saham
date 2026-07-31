"""
Broker provider construction for `saham fetch market` and related commands.

Selects between the Stockbit and IDX broker data provider implementations
based on an explicit CLI choice or Stockbit session auto-detection. This is
adapter-level dependency wiring — selecting which concrete infrastructure
implementation to construct — not fetch/cache policy.

Layer: Adapter
"""

from src.infrastructure.data_providers.idx import IdxBrokerDataProvider


def create_broker_provider(name: str | None):
    """
    Create broker provider by explicit name, or auto-detect if name is None.

    The returned provider is used for broker_daily_flow, foreign_flow_points, and optionally
    broker_summaries. Summary source is controlled by preferences.broker_summary_source in
    config/stockbit.yaml (default: idx). Stockbit is valid since it now uses
    /company-price-feed/historical/summary for true total_value.

    Auto-detect order:
      1. Playwright session (.stockbit_profile/) — preferred; no token file needed
      2. IDX public API — always available fallback
    """
    from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider
    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session

    if name == "stockbit":
        stockbit_config = load_stockbit_provider_config()
        session = get_stockbit_session(stockbit_config)
        if session and session.authenticated:
            provider = StockbitBrokerProvider(session.api_client, stockbit_config=stockbit_config)
            return provider, "stockbit"
        return IdxBrokerDataProvider(), "idx"
    if name == "idx":
        return IdxBrokerDataProvider(), "idx"
    if name is not None:
        raise ValueError(f"Unknown broker provider: {name}. Choose from: idx, stockbit")

    # Auto-detect
    stockbit_config = load_stockbit_provider_config()
    session = get_stockbit_session(stockbit_config)
    if session and session.authenticated:
        provider = StockbitBrokerProvider(session.api_client, stockbit_config=stockbit_config)
        return provider, "stockbit"
    return IdxBrokerDataProvider(), "idx"
