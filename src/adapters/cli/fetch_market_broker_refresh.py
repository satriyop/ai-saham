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

from datetime import date, datetime
from pathlib import Path

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
    EffectiveMarketSessionResolver,
)
from src.application.services.market_freshness_service import MarketFreshnessService
from src.application.use_case.fetch_market_refresh_use_case import BrokerFetchResult
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
    canonicalize_ticker,
    is_benchmark_ticker,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import load_app_config
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
    # injectable for testing; production code uses IdxBrokerDataProvider
    _idx_summary_provider=None,
    effective_session: EffectiveMarketSession | None = None,
) -> BrokerFetchResult:
    """Fetch broker flow for one ticker. Returns split status for summaries and flow tables."""
    cfg = load_app_config()
    market_start_tolerance_days = cfg.fetch.start_tolerance_days

    ticker = canonicalize_ticker(ticker)
    if is_benchmark_ticker(ticker) or ticker.startswith("^"):
        return BrokerFetchResult(summaries="n/a:index", flow="n/a:index")

    end_date = date.today()
    repo = SQLiteBrokerRepository(db_path)
    idx_summary_provider = _resolve_idx_summary_provider(broker_provider, _idx_summary_provider)

    from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider

    notation_repo = StockbitTickerNotationProvider(
        api_client=None, db_path=db_path, stockbit_config=load_stockbit_provider_config()
    )

    freshness = MarketFreshnessService()
    if effective_session is None:
        # No shared command-level session was injected (e.g. this helper was
        # called directly, not through FetchMarketRefreshUseCase) — resolve
        # one locally so resolve_reference_trading_day still has a session.
        market_repo = SQLiteMarketRepository(db_path=db_path)
        now_wib = datetime.now(IDX_TIMEZONE)
        run_at = datetime.combine(end_date, now_wib.time(), tzinfo=IDX_TIMEZONE)
        effective_session = EffectiveMarketSessionResolver(market_repo).resolve(run_at=run_at)
    last_trading_day = freshness.resolve_reference_trading_day(effective_session, end_date)

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
            requested_start_tolerance_days=market_start_tolerance_days,
        )
    )
    if short_history is not None:
        short_history.extend(response.notes)
    return BrokerFetchResult(
        summaries=response.summaries_status,
        flow=response.flow_status,
    )
