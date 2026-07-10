"""
Broker flow refresh wiring for `saham fetch market`.

Constructs the concrete IDX summary provider named by
ResolveBrokerSummaryProviderPolicyUseCase's decision and drives
RefreshBrokerDataUseCase for one ticker. Cache-tolerance policy is owned by
MarketFreshnessService; summary-provider *selection* policy is owned by
ResolveBrokerSummaryProviderPolicyUseCase. This module only wires
infrastructure implementations to those decisions.

Layer: Adapter
"""

from datetime import date
from pathlib import Path

from src.application.services.market_freshness_service import (
    BenchmarkTickerAliases,
    MarketFreshnessService,
)
from src.application.use_case.fetch_market_refresh_use_case import (
    BENCHMARK_TICKER,
    BrokerFetchResult,
)
from src.application.use_case.refresh_broker_data_use_case import (
    RefreshBrokerDataRequest,
    RefreshBrokerDataUseCase,
)
from src.application.use_case.resolve_broker_summary_provider_policy_use_case import (
    BrokerSummaryProviderKind,
    ResolveBrokerSummaryProviderPolicyRequest,
    ResolveBrokerSummaryProviderPolicyUseCase,
)
from src.domain.value_objects.benchmark_symbol import (
    YAHOO_IHSG_TICKER,
    canonicalize_ticker,
    is_benchmark_ticker,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.data_sources_config import (
    broker_summary_source as _broker_summary_source,
)
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

_BENCHMARK_ALIASES = BenchmarkTickerAliases(canonical=BENCHMARK_TICKER, legacy=YAHOO_IHSG_TICKER)

# How many calendar days of gap at the START of a requested range is tolerable
# before triggering a backfill.
MARKET_START_TOLERANCE_DAYS: int = APP_CFG.fetch.start_tolerance_days


def _resolve_idx_summary_provider(broker_provider, _idx_summary_provider):
    if _idx_summary_provider is not None:
        return _idx_summary_provider
    decision = ResolveBrokerSummaryProviderPolicyUseCase().execute(
        ResolveBrokerSummaryProviderPolicyRequest(
            broker_provider_name=broker_provider.provider_name,
            configured_summary_source=_broker_summary_source(),
        )
    )
    if decision.kind == BrokerSummaryProviderKind.REUSE_BROKER_PROVIDER:
        return broker_provider
    return IdxBrokerDataProvider()


def fetch_broker(
    ticker: str,
    days: int,
    db_path: Path,
    broker_provider,
    refresh: bool,
    short_history: list[str] | None = None,
    _idx_summary_provider=None,  # injectable for testing; production code uses IdxBrokerDataProvider
) -> BrokerFetchResult:
    """Fetch broker flow for one ticker. Returns split status for summaries and flow tables."""
    ticker = canonicalize_ticker(ticker)
    if is_benchmark_ticker(ticker) or ticker.startswith("^"):
        return BrokerFetchResult(summaries="n/a:index", flow="n/a:index")

    end_date = date.today()
    repo = SQLiteBrokerRepository(db_path)
    idx_summary_provider = _resolve_idx_summary_provider(broker_provider, _idx_summary_provider)

    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider

    notation_repo = StockbitTickerNotationProvider(api_client=None, db_path=db_path)

    freshness = MarketFreshnessService(repository=SQLiteMarketRepository(db_path=db_path))
    last_trading_day = freshness.resolve_reference_trading_day(_BENCHMARK_ALIASES, end_date)

    response = RefreshBrokerDataUseCase(
        broker_provider=broker_provider,
        idx_summary_provider=idx_summary_provider,
        repository=repo,
        notation_repository=notation_repo,
    ).execute(
        RefreshBrokerDataRequest(
            ticker=ticker,
            days=days,
            refresh=refresh,
            end_date=end_date,
            last_trading_day=last_trading_day,
            requested_start_tolerance_days=MARKET_START_TOLERANCE_DAYS,
        )
    )
    if short_history is not None:
        short_history.extend(response.notes)
    return BrokerFetchResult(
        summaries=response.summaries_status,
        flow=response.flow_status,
    )
