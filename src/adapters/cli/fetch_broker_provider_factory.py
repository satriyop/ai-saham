"""
Provider factory for broker data providers.

Layer: Adapter (composition root / infrastructure wiring helper)
"""

from src.domain.ports.broker_data_provider import BrokerDataProvider
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider

PROVIDERS = ("idx", "stockbit")


def create_broker_data_provider(provider_name: str) -> BrokerDataProvider:
    """Create a broker data provider by name.

    Raises:
        ValueError: If provider_name is unknown or if a Stockbit session is inactive.
    """
    if provider_name == "idx":
        return IdxBrokerDataProvider()
    elif provider_name == "stockbit":
        from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider
        from src.infrastructure.composition.stockbit_session_factory import get_stockbit_session
        session = get_stockbit_session()
        if not session or not session.authenticated:
            raise ValueError("No active Stockbit session. Run `saham fetch stockbit login`.")
        return StockbitBrokerProvider(session.api_client)
    else:
        raise ValueError(
            f"Unknown provider: {provider_name}. Choose from: {', '.join(PROVIDERS)}"
        )
