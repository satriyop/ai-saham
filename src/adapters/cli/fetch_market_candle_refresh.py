"""
Candle refresh wiring for `saham fetch market`.

Constructs the concrete candle provider named by
ResolveCandleProviderPolicyUseCase's decision and drives
RefreshMarketDataUseCase for one ticker. Cache-tolerance policy is owned by
MarketFreshnessService; provider *selection* policy is owned by
ResolveCandleProviderPolicyUseCase. This module only wires infrastructure
implementations to those decisions.

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.browser.stockbit_broker_provider import StockbitBrokerProvider

from src.application.services.market_freshness_service import (
    BenchmarkTickerAliases,
    MarketFreshnessService,
)
from src.application.use_case.fetch_market_refresh_use_case import BENCHMARK_TICKER
from src.application.use_case.refresh_market_data_use_case import (
    RefreshMarketDataRequest,
    RefreshMarketDataUseCase,
)
from src.application.use_case.resolve_candle_provider_policy_use_case import (
    CandleProviderKind,
    ResolveCandleProviderPolicyRequest,
    ResolveCandleProviderPolicyUseCase,
)
from src.domain.value_objects.benchmark_symbol import (
    YAHOO_IHSG_TICKER,
    canonicalize_ticker,
    is_benchmark_ticker,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.data_providers.stockbit_historical import StockbitHistoricalProvider
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

# Benchmark ticker always included in every market refresh run (first in list).
# Required by: saham analyze regime, saham analyze swing (market context).
_BENCHMARK_TICKER = BENCHMARK_TICKER
_BENCHMARK_ALIASES = BenchmarkTickerAliases(canonical=_BENCHMARK_TICKER, legacy=YAHOO_IHSG_TICKER)


def _construct_provider(
    kind: CandleProviderKind,
    non_idx: set[str],
    broker_provider: "StockbitBrokerProvider | None",
):
    if kind == CandleProviderKind.YAHOO:
        return YahooFinanceProvider(non_idx_tickers=non_idx)
    if kind == CandleProviderKind.STOCKBIT_HISTORICAL:
        return StockbitHistoricalProvider(api_client=broker_provider.api_client, non_idx_tickers=non_idx)
    from src.infrastructure.data_providers.idx_market import IdxMarketDataProvider

    return IdxMarketDataProvider()


def fetch_candles(
    ticker: str,
    days: int,
    db_path: Path,
    provider_name: str,
    refresh: bool,
    short_history: list[str] | None = None,
    broker_provider: "StockbitBrokerProvider | None" = None,
) -> str:
    """Fetch candles for one ticker. Returns status string."""
    from src.infrastructure.config.market_context_config import get_global_context_tickers

    cfg = load_app_config()
    market_start_tolerance_days = cfg.fetch.start_tolerance_days

    ticker = canonicalize_ticker(ticker)
    non_idx = get_global_context_tickers()

    decision = ResolveCandleProviderPolicyUseCase().execute(
        ResolveCandleProviderPolicyRequest(
            ticker=ticker,
            non_idx_tickers=frozenset(non_idx),
            requested_provider_name=provider_name,
            has_broker_session=broker_provider is not None,
        )
    )
    if decision.error is not None:
        raise ValueError(decision.error)

    provider = _construct_provider(decision.provider_kind, non_idx, broker_provider)

    repo = SQLiteMarketRepository(db_path=db_path)
    use_case = RefreshMarketDataUseCase(provider=provider, repository=repo)
    freshness = MarketFreshnessService(repository=repo)

    try:
        today = date.today()
        end_tolerance = freshness.end_tolerance_days(
            is_benchmark=is_benchmark_ticker(ticker),
            benchmark=_BENCHMARK_ALIASES,
            today=today,
        )

        response = use_case.execute(
            RefreshMarketDataRequest(
                ticker=ticker,
                days=days,
                refresh=refresh,
                start_tolerance_days=market_start_tolerance_days,
                end_tolerance_days=end_tolerance,
            )
        )
        if short_history is not None and response.short_history_note:
            short_history.append(response.short_history_note)

        # Embed the latest date into "cached-current" for display clarity
        if response.status == "cached-current" and response.date_range:
            return f"✓({response.date_range[1]})"
        return response.status
    except Exception as e:
        return f"ERR:{str(e)[:30]}"
