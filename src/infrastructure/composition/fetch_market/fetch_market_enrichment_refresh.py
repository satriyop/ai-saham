"""
Stockbit enrichment refresh helpers for `saham fetch market` and
`saham fetch enrichment-history`.

Owns the enrichment provider fan-out (notation, analyst, insider,
seasonality, corporate actions, shareholding, bandar, fundamentals,
forward estimates, company profile, earnings, broker distribution,
valuation) and delegates cache-freshness-then-fetch policy to
RefreshStockbitEnrichmentUseCase. Also owns the point-in-time enrichment
coverage read used to render post-run PIT coverage summaries.

Layer: Infrastructure composition
"""

from datetime import date, timedelta
from pathlib import Path

from src.domain.value_objects.benchmark_symbol import canonicalize_ticker, is_benchmark_ticker


def fetch_enrichment(
    ticker: str,
    db_path: Path,
    broker_provider,
    *,
    force_refresh: bool = False,
) -> str:
    """Pre-fetch Stockbit enrichment data for one ticker into SQLite cache.

    Delegates cache-freshness-then-fetch policy to RefreshStockbitEnrichmentUseCase.
    Returns a compact status string, e.g. "analyst+bandar  ✓(insider,season,corp,holding)".
    """
    if broker_provider is None:
        return "skip:no-stockbit"
    ticker = canonicalize_ticker(ticker)
    if is_benchmark_ticker(ticker) or ticker.startswith("^"):
        return "n/a:index"

    from src.application.use_case.refresh_stockbit_enrichment_use_case import (
        EnrichmentTask,
        RefreshStockbitEnrichmentRequest,
        RefreshStockbitEnrichmentUseCase,
    )
    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_broker_distribution import (
        StockbitBrokerDistributionProvider,
    )
    from src.infrastructure.browser.stockbit_company_profile import StockbitCompanyProfileProvider
    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
    from src.infrastructure.browser.stockbit_earnings import StockbitEarningsProvider
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )
    from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
    from src.infrastructure.browser.stockbit_sqlite_connection_provider import (
        StockbitSQLiteConnectionProvider,
    )
    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
    from src.infrastructure.browser.stockbit_valuation import StockbitValuationProvider

    today = date.today()
    insider_from = today - timedelta(days=365)

    _api_client = broker_provider.api_client
    connection_provider = StockbitSQLiteConnectionProvider()
    stockbit_config = load_stockbit_provider_config()
    analyst_prov = StockbitAnalystConsensusProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    insider_prov = StockbitInsiderActivityProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    season_prov = StockbitSeasonalityProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    corp_repo = StockbitCorporateActionRepository(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    shareholding_prov = StockbitShareholdingProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    bandar_prov = StockbitBandarDetectorProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    fundamentals_prov = StockbitFundamentalsProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    notation_prov = StockbitTickerNotationProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    fwd_est_prov = StockbitForwardEstimatesProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    profile_prov = StockbitCompanyProfileProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    earnings_prov = StockbitEarningsProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    distribution_prov = StockbitBrokerDistributionProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )
    valuation_prov = StockbitValuationProvider(
        api_client=_api_client,
        db_path=db_path,
        connection_provider=connection_provider,
        stockbit_config=stockbit_config,
    )

    tasks = [
        EnrichmentTask(
            "notation",
            lambda: notation_prov.is_cache_fresh(ticker),
            lambda: notation_prov.get_notation(ticker),
        ),
        EnrichmentTask(
            "analyst",
            lambda: analyst_prov._is_cache_fresh(ticker),
            lambda: analyst_prov.get_consensus(ticker),
        ),
        EnrichmentTask(
            "insider",
            lambda: insider_prov._is_cache_fresh(ticker),
            lambda: insider_prov.get_insider_transactions(ticker, insider_from, today, "ALL"),
        ),
        EnrichmentTask(
            "season",
            lambda: season_prov._is_cache_fresh(ticker, today.year, today.month),
            lambda: season_prov.get_seasonal_edge(ticker, today.year, today.month),
        ),
        EnrichmentTask(
            "corp",
            lambda: corp_repo._is_cache_fresh(ticker),
            lambda: corp_repo.get_upcoming_events(ticker, today, today + timedelta(days=90)),
        ),
        EnrichmentTask(
            "holding",
            lambda: shareholding_prov._is_cache_fresh(ticker),
            lambda: shareholding_prov.get_composition(ticker),
        ),
        EnrichmentTask(
            "bandar",
            lambda: bandar_prov._is_cache_fresh(ticker),
            lambda: bandar_prov.get_snapshot(ticker),
        ),
        EnrichmentTask(
            "fundam",
            lambda: fundamentals_prov._is_cache_fresh(ticker),
            lambda: fundamentals_prov.get_fundamentals(ticker),
        ),
        EnrichmentTask(
            "fwd_est",
            lambda: fwd_est_prov._read_cache(ticker) is not None,
            lambda: fwd_est_prov.get_forward_estimates(ticker),
        ),
        EnrichmentTask(
            "profile",
            lambda: profile_prov._read_cache(ticker) is not None,
            lambda: profile_prov.get_profile(ticker),
        ),
        EnrichmentTask(
            "earnings",
            lambda: earnings_prov.is_cache_fresh(ticker),
            lambda: earnings_prov.get_earnings_history(ticker),
        ),
        EnrichmentTask(
            "brdist",
            lambda: distribution_prov.is_cache_fresh(ticker),
            lambda: distribution_prov.get_distribution(ticker),
        ),
        EnrichmentTask(
            "valuation",
            lambda: valuation_prov.is_cache_fresh(ticker),
            lambda: valuation_prov.get_valuation(ticker),
        ),
    ]
    return (
        RefreshStockbitEnrichmentUseCase()
        .execute(
            RefreshStockbitEnrichmentRequest(
                ticker=ticker,
                tasks=tasks,
                force_refresh=force_refresh,
            )
        )
        .status
    )


def read_enrichment_pit_coverage(db_path: Path):
    """Delegate PIT coverage read to the infrastructure persistence layer."""
    from src.infrastructure.persistence.sqlite_enrichment_pit_coverage import (
        read_enrichment_pit_coverage as _read_enrichment_pit_coverage,
    )

    return _read_enrichment_pit_coverage(db_path)
