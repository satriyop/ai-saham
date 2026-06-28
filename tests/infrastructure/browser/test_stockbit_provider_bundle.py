from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)


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
    assert providers.analyst_prov._provider is None
    assert providers.bandar_prov._provider is None
    assert providers.forward_estimates_prov._provider is None
