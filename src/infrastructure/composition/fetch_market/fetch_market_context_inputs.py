"""
Adapter wiring for MarketContextEngine + sector-macro global context refresh.

Loads market-context config, resolves which global context tickers
(^VIX, EIDO, IDR=X, etc.) are enabled, appends ADR-053 sector-macro
*live-map* series (e.g. CL=F, CPO=F) even when MCE commodity_composite is
off, constructs the no-suffix Yahoo provider and SQLite market repository
exactly once, and drives RefreshMarketContextInputsUseCase with an injected
per-ticker refresh callable.

This module owns all infrastructure construction so the use case itself
never imports from src.infrastructure.

Global context tickers are not IDX stocks and must never receive the
`.JK` suffix applied to regular IDX tickers — enforced here via
`market_suffix=""`.

Layer: Infrastructure composition
"""

from pathlib import Path

from src.application.use_case.refresh_market_context_inputs_use_case import (
    GlobalContextTickerInput,
    RefreshMarketContextInputsRequest,
    RefreshMarketContextInputsResponse,
    RefreshMarketContextInputsUseCase,
)
from src.application.use_case.refresh_market_data_use_case import (
    RefreshMarketDataRequest,
    RefreshMarketDataUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_config import (
    get_global_context_tickers,
    load_market_context_config,
)
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

DEFAULT_GLOBAL_CONTEXT_DAYS: int = 180


def refresh_market_context_inputs(
    db_path: Path, days: int = DEFAULT_GLOBAL_CONTEXT_DAYS
) -> RefreshMarketContextInputsResponse:
    """Refresh MCE + sector-macro global series for `saham fetch market`."""
    cfg_app = load_app_config()
    market_start_tolerance_days = cfg_app.fetch.start_tolerance_days

    cfg = load_market_context_config()
    end_tol = cfg.fetch.global_context_end_tolerance_days
    ticker_inputs: list[GlobalContextTickerInput] = []
    seen: set[str] = set()

    def _add(ticker: str, factor: str) -> None:
        key = str(ticker).upper().strip()
        if not key or key in seen:
            return
        seen.add(key)
        ticker_inputs.append(
            GlobalContextTickerInput(
                ticker=key,
                factor=factor,
                end_tolerance_days=end_tol,
            )
        )

    if cfg.vix.enabled:
        _add(cfg.vix.ticker, "vix")
    if cfg.eido.enabled:
        _add(cfg.eido.ticker, "eido")
    if cfg.usd_idr.enabled:
        _add(cfg.usd_idr.ticker, "usd_idr")

    # ADR-053: always hydrate live sector-macro map series (CL=F, CPO=F, …)
    # so plan swing energy/plantation macro does not depend on a manual
    # explicit ticker fetch. Dedupes against MCE tickers (e.g. IDR=X).
    try:
        from src.infrastructure.config.sector_macro_context_config_loader import (
            required_sector_macro_series_tickers,
        )

        for series in sorted(required_sector_macro_series_tickers()):
            _add(series, "sector_macro")
    except Exception:
        pass

    if not ticker_inputs:
        return RefreshMarketContextInputsResponse(statuses=())

    provider = YahooFinanceProvider(market_suffix="", non_idx_tickers=get_global_context_tickers())
    repo = SQLiteMarketRepository(db_path=db_path)
    market_data_use_case = RefreshMarketDataUseCase(provider=provider, repository=repo)

    def _refresh_ticker(ticker: str, refresh_days: int, end_tolerance_days: int) -> str:
        resp = market_data_use_case.execute(
            RefreshMarketDataRequest(
                ticker=ticker,
                days=refresh_days,
                refresh=False,
                start_tolerance_days=market_start_tolerance_days,
                end_tolerance_days=end_tolerance_days,
            )
        )
        return resp.status

    return RefreshMarketContextInputsUseCase().execute(
        RefreshMarketContextInputsRequest(
            tickers=tuple(ticker_inputs),
            days=days,
            refresh_ticker=_refresh_ticker,
        )
    )
