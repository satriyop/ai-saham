"""
Adapter wiring for MarketContextEngine global context ticker refresh.

Loads market-context config, resolves which global context tickers
(^VIX, EIDO, IDR=X, etc.) are enabled, constructs the no-suffix Yahoo
provider and SQLite market repository exactly once, and drives
RefreshMarketContextInputsUseCase with an injected per-ticker refresh
callable. This module owns all infrastructure construction so the
use case itself never imports from src.infrastructure.

Global context tickers are not IDX stocks and must never receive the
`.JK` suffix applied to regular IDX tickers — enforced here via
`market_suffix=""`.

Layer: Adapter
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
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.market_context_config import (
    get_global_context_tickers,
    load_market_context_config,
)
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

DEFAULT_GLOBAL_CONTEXT_DAYS: int = 180
MARKET_START_TOLERANCE_DAYS: int = APP_CFG.fetch.start_tolerance_days


def refresh_market_context_inputs(
    db_path: Path, days: int = DEFAULT_GLOBAL_CONTEXT_DAYS
) -> RefreshMarketContextInputsResponse:
    """Refresh all enabled MCE global context tickers for `saham fetch market`."""
    cfg = load_market_context_config()
    ticker_inputs: list[GlobalContextTickerInput] = []

    if cfg.vix.enabled:
        ticker_inputs.append(
            GlobalContextTickerInput(
                ticker=cfg.vix.ticker,
                factor="vix",
                end_tolerance_days=cfg.fetch.global_context_end_tolerance_days,
            )
        )
    if cfg.eido.enabled:
        ticker_inputs.append(
            GlobalContextTickerInput(
                ticker=cfg.eido.ticker,
                factor="eido",
                end_tolerance_days=cfg.fetch.global_context_end_tolerance_days,
            )
        )
    if cfg.usd_idr.enabled:
        ticker_inputs.append(
            GlobalContextTickerInput(
                ticker=cfg.usd_idr.ticker,
                factor="usd_idr",
                end_tolerance_days=cfg.fetch.global_context_end_tolerance_days,
            )
        )

    if not ticker_inputs:
        return RefreshMarketContextInputsResponse(statuses=())

    provider = YahooFinanceProvider(
        market_suffix="", non_idx_tickers=get_global_context_tickers()
    )
    repo = SQLiteMarketRepository(db_path=db_path)
    market_data_use_case = RefreshMarketDataUseCase(provider=provider, repository=repo)

    def _refresh_ticker(ticker: str, refresh_days: int, end_tolerance_days: int) -> str:
        resp = market_data_use_case.execute(
            RefreshMarketDataRequest(
                ticker=ticker,
                days=refresh_days,
                refresh=False,
                start_tolerance_days=MARKET_START_TOLERANCE_DAYS,
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
