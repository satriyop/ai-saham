"""
Factory for construction and dependency injection of fetch market command workflow usecase.

Layer: Infrastructure composition
"""

import functools
from pathlib import Path
from typing import Any

import src.infrastructure.composition.fetch_market.fetch_market_calendar_refresh as _calendar_mod
import src.infrastructure.composition.fetch_market.fetch_market_context_inputs as _context_mod
from src.infrastructure.composition.fetch_market.fetch_market_broker_refresh import fetch_broker
from src.infrastructure.composition.fetch_market.fetch_market_candle_refresh import fetch_candles
from src.infrastructure.composition.fetch_market.fetch_market_enrichment_refresh import (
    fetch_enrichment,
    read_enrichment_pit_coverage,
)
from src.infrastructure.composition.fetch_market.fetch_market_meta_refresh import fetch_meta
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.fetch_market_provider_precondition import (
    FetchMarketProviderPrecondition,
)
from src.application.services.market_freshness_service import MarketFreshnessService
from src.application.services.universe_loader import resolve_tickers
from src.application.use_case.fetch_market_command_workflow_use_case import (
    FetchMarketCommandWorkflowUseCase,
    FetchMarketStatusHeader,
)
from src.application.use_case.fetch_market_refresh_use_case import (
    FetchMarketRefreshUseCase,
)
from src.infrastructure.config.market_context_config import get_global_context_tickers
from src.infrastructure.config.universe_config_loader import YamlUniverseConfigLoader
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def create_workflow_use_case(
    db_path: Path,
    broker_provider: Any,
    broker_provider_name: str,
) -> FetchMarketCommandWorkflowUseCase:
    """Wire dependencies and build FetchMarketCommandWorkflowUseCase.

    All concrete infrastructure classes, configuration loaders, and database repositories
    are resolved and injected here to keep the CLI commands and the application layer pure.
    """
    _candles_fn = (
        functools.partial(fetch_candles, broker_provider=broker_provider)
        if broker_provider_name == "stockbit"
        else fetch_candles
    )
    _read_coverage_fn = functools.partial(read_enrichment_pit_coverage, db_path)

    refresh_use_case = FetchMarketRefreshUseCase(
        fetch_candles=_candles_fn,
        fetch_broker=fetch_broker,
        fetch_meta=fetch_meta,
        fetch_enrichment=fetch_enrichment,
        universe_loader=YamlUniverseConfigLoader(),
        broker_repository=SQLiteBrokerRepository(db_path),
        read_pit_coverage=_read_coverage_fn,
    )

    provider_precondition = FetchMarketProviderPrecondition()

    def non_idx_tickers_loader() -> frozenset[str]:
        return frozenset(get_global_context_tickers())

    def market_status_loader() -> FetchMarketStatusHeader | None:
        from src.infrastructure.browser.stockbit_market_time import (
            fetch_and_cache_market_status,
            format_market_status_line,
            get_display_market_status,
        )
        mstatus = fetch_and_cache_market_status() or get_display_market_status()
        if mstatus is None:
            return None
        line = format_market_status_line(mstatus)
        return FetchMarketStatusHeader(line=line, is_open=mstatus.is_open)

    def calendar_refresh_wrapper(resolved_db: Path, api_client: Any, refresh: bool) -> str:
        return _calendar_mod.refresh_market_calendar(
            db_path=resolved_db,
            api_client=api_client,
            refresh=refresh,
        )

    def context_refresh_wrapper(resolved_db: Path, days: int):
        return _context_mod.refresh_market_context_inputs(resolved_db, days=days)

    market_freshness = MarketFreshnessService()
    session_resolver = EffectiveMarketSessionResolver(
        SQLiteMarketRepository(db_path=db_path)
    )

    def ticker_resolver(universe: str | None, explicit: list[str], db_path: Path) -> list[str]:
        return resolve_tickers(
            universe=universe,
            explicit=explicit,
            db_path=db_path,
            loader=YamlUniverseConfigLoader(),
            repository=SQLiteBrokerRepository(db_path),
        )

    return FetchMarketCommandWorkflowUseCase(
        refresh_use_case=refresh_use_case,
        provider_precondition=provider_precondition,
        non_idx_tickers_loader=non_idx_tickers_loader,
        market_status_loader=market_status_loader,
        calendar_refresh=calendar_refresh_wrapper,
        context_refresh=context_refresh_wrapper,
        market_freshness=market_freshness,
        ticker_resolver=ticker_resolver,
        session_resolver=session_resolver,
    )
