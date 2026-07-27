import src.infrastructure.browser.stockbit_provider_bundle as bundle_module
from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)
from src.infrastructure.config.stockbit_config import StockbitConfig


def test_create_readonly_stockbit_providers_uses_cache_only(tmp_path):
    providers = create_readonly_stockbit_providers(tmp_path / "data.db")

    assert providers.corp_repo is not None
    assert providers.season_prov is not None
    assert providers.insider_prov is not None
    assert providers.analyst_prov is not None
    assert providers.shareholding_prov is not None
    assert providers.bandar_prov is not None
    assert providers.fundamentals_prov is not None
    assert providers.notation_prov is not None
    assert providers.forward_estimates_prov is not None
    assert providers.analyst_prov._api_client is None
    assert providers.bandar_prov._api_client is None
    assert providers.forward_estimates_prov._api_client is None


def test_create_readonly_stockbit_providers_loads_config_once_and_shares_it(tmp_path, monkeypatch):
    """Config must be loaded exactly once and the same instance shared."""
    calls = []

    def _fake_load_config() -> StockbitConfig:
        cfg = StockbitConfig()
        calls.append(cfg)
        return cfg

    monkeypatch.setattr(bundle_module, "load_stockbit_provider_config", _fake_load_config)

    providers = create_readonly_stockbit_providers(tmp_path / "data.db")

    assert len(calls) == 1
    shared_config = calls[0]
    assert providers.corp_repo._stockbit_config is shared_config
    assert providers.season_prov._stockbit_config is shared_config
    assert providers.insider_prov._stockbit_config is shared_config
    assert providers.analyst_prov._stockbit_config is shared_config
    assert providers.shareholding_prov._stockbit_config is shared_config
    assert providers.bandar_prov._stockbit_config is shared_config
    assert providers.fundamentals_prov._stockbit_config is shared_config
    assert providers.notation_prov._stockbit_config is shared_config
    assert providers.forward_estimates_prov._stockbit_config is shared_config
