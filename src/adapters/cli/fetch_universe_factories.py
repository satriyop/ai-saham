"""
Factory helpers for universe CLI commands.

Layer: Adapter
"""

import src.infrastructure.browser.stockbit_universe as _stockbit_universe
import src.infrastructure.composition.stockbit_session_factory as _stockbit_session
from src.application.ports.universe_config_store import UniverseConfigStore
from src.application.use_case.manage_universe_use_case import (
    CreateUniverseUseCase,
    InspectUniverseUseCase,
    UpdateUniverseUseCase,
)
from src.infrastructure.browser.stockbit_api_client import StockbitApiClient
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.config.stockbit_config import StockbitConfig


def _require_api_client() -> tuple[StockbitApiClient, StockbitConfig]:
    """Get authenticated Stockbit API client (and the config used to build it) or exit."""
    stockbit_config = load_stockbit_provider_config()
    _session = _stockbit_session.get_stockbit_session(stockbit_config)
    if not _session or not _session.authenticated:
        from typer import Exit, echo

        echo("Stockbit session expired. Run `saham fetch stockbit login` to refresh.")
        raise Exit(1)
    return _session.api_client, stockbit_config


class _ProviderAdapter:
    """Adapter that satisfies UniverseCatalogProvider protocol.

    Wraps StockbitUniverseProvider (list_available, fetch) and the raw
    API client (get) into a single object the use cases can consume.
    """

    def __init__(
        self, prov: _stockbit_universe.StockbitUniverseProvider, client: StockbitApiClient
    ) -> None:
        self._prov = prov
        self._client = client

    def list_available(self) -> dict[str, tuple[int | str, int]]:
        return self._prov.list_available()

    def fetch(self, key: str) -> list[str]:
        return self._prov.fetch(key)

    def get(self, url: str) -> dict | None:
        return self._client.get(url)


def create_provider_adapter() -> _ProviderAdapter:
    """Create provider adapter with authenticated API client."""
    api_client, stockbit_config = _require_api_client()
    universe_prov = _stockbit_universe.StockbitUniverseProvider(
        api_client=api_client, stockbit_config=stockbit_config
    )
    return _ProviderAdapter(universe_prov, api_client)


def create_update_use_case(
    provider: _ProviderAdapter,
    config_store: UniverseConfigStore,
) -> UpdateUniverseUseCase:
    """Create UpdateUniverseUseCase with standard dependencies."""
    return UpdateUniverseUseCase(
        provider=provider,
        config_store=config_store,
        universe_type=_stockbit_universe.universe_type,
        sleep=__import__("time").sleep,
    )


def create_inspect_use_case(
    provider: _ProviderAdapter,
) -> InspectUniverseUseCase:
    """Create InspectUniverseUseCase with standard dependencies."""
    return InspectUniverseUseCase(provider=provider)


def create_create_use_case(
    provider: _ProviderAdapter,
    config_store: UniverseConfigStore,
) -> CreateUniverseUseCase:
    """Create CreateUniverseUseCase with standard dependencies."""
    return CreateUniverseUseCase(
        provider=provider,
        config_store=config_store,
        sleep=__import__("time").sleep,
    )
