"""
Stockbit provider bundle helpers.

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
from src.infrastructure.browser.stockbit_forward_estimates import StockbitForwardEstimatesProvider
from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
from src.infrastructure.browser.stockbit_providers import StockbitProviders
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
    StockbitSQLiteConnectionProvider,
)
from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider


def create_readonly_stockbit_providers(db_path: Path) -> StockbitProviders:
    """Return Stockbit providers backed by SQLite cache only.

    `api_client=None` keeps this bundle read-only: providers return cached
    enrichment when present and do not open a browser or hit Stockbit live APIs.

    Loads `StockbitConfig` once and passes the same instance into every
    provider constructed here, instead of each provider loading its own copy.
    """
    connection_provider = StockbitSQLiteConnectionProvider()
    stockbit_config = load_stockbit_provider_config()
    return StockbitProviders(
        corp_repo=StockbitCorporateActionRepository(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        season_prov=StockbitSeasonalityProvider(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        insider_prov=StockbitInsiderActivityProvider(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        analyst_prov=StockbitAnalystConsensusProvider(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        shareholding_prov=StockbitShareholdingProvider(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        bandar_prov=StockbitBandarDetectorProvider(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        fundamentals_prov=StockbitFundamentalsProvider(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        notation_prov=StockbitTickerNotationProvider(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
        forward_estimates_prov=StockbitForwardEstimatesProvider(
            api_client=None,
            db_path=db_path,
            connection_provider=connection_provider,
            stockbit_config=stockbit_config,
        ),
    )
