"""
Stockbit provider bundle helpers.

Layer: Infrastructure
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
from src.infrastructure.browser.stockbit_forward_estimates import StockbitForwardEstimatesProvider
from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
from src.infrastructure.browser.stockbit_providers import StockbitProviders
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider


def create_readonly_stockbit_providers(db_path: Path) -> StockbitProviders:
    """Return Stockbit providers backed by SQLite cache only.

    `api_client=None` keeps this bundle read-only: providers return cached
    enrichment when present and do not open a browser or hit Stockbit live APIs.
    """
    return StockbitProviders(
        corp_repo=StockbitCorporateActionRepository(api_client=None, db_path=db_path),
        season_prov=StockbitSeasonalityProvider(api_client=None, db_path=db_path),
        insider_prov=StockbitInsiderActivityProvider(api_client=None, db_path=db_path),
        analyst_prov=StockbitAnalystConsensusProvider(api_client=None, db_path=db_path),
        shareholding_prov=StockbitShareholdingProvider(api_client=None, db_path=db_path),
        bandar_prov=StockbitBandarDetectorProvider(api_client=None, db_path=db_path),
        fundamentals_prov=StockbitFundamentalsProvider(api_client=None, db_path=db_path),
        notation_prov=StockbitTickerNotationProvider(api_client=None, db_path=db_path),
        forward_estimates_prov=StockbitForwardEstimatesProvider(
            api_client=None,
            db_path=db_path,
        ),
    )
