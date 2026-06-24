"""
CLI command for market data refresh.

Provides `saham fetch market` — a single daily command to fetch fresh
candles + broker flow for a stock universe or explicit ticker list.

Auto-selects broker provider: Stockbit if token is available, IDX otherwise.

Usage:
    saham fetch market --universe lq45          # all LQ45 stocks
    saham fetch market --universe cached        # refresh already-cached tickers
    saham fetch market BBCA BBRI BMRI           # explicit tickers
    saham fetch market --universe lq45 --days 30
    saham fetch market --universe lq45 --broker-only

Layer: Adapter
"""

import functools
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Optional

if TYPE_CHECKING:
    from src.infrastructure.browser.playwright_stockbit_provider import StockbitPlaywrightBrokerProvider

import typer

from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.fetch_market_refresh_use_case import (
    BENCHMARK_TICKER,
    BrokerFetchResult,
    FetchMarketRefreshRequest,
    FetchMarketRefreshUseCase,
)
from src.application.use_case.fetch_stock_meta_use_case import (
    FetchStockMetaRequest,
    FetchStockMetaUseCase,
)
from src.application.use_case.refresh_broker_data_use_case import (
    RefreshBrokerDataRequest,
    RefreshBrokerDataUseCase,
)
from src.application.use_case.refresh_market_data_use_case import (
    RefreshMarketDataRequest,
    RefreshMarketDataUseCase,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.data_sources_config import (
    broker_summary_source as _broker_summary_source,
)
from src.infrastructure.config.data_sources_config import (
    candle_source as _candle_source,
)
from src.infrastructure.data_providers.fallback_provider import FallbackMarketDataProvider
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider
from src.infrastructure.data_providers.stockbit_historical import StockbitHistoricalProvider
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.data_providers.yahoo_stock_meta import YahooStockMetaProvider
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)
from src.infrastructure.persistence.sqlite_data_update_status import (
    build_data_update_table_statuses,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)
from src.infrastructure.persistence.sqlite_stock_meta_repository import (
    SQLiteStockMetaRepository,
)

DEFAULT_DAYS: int = APP_CFG.fetch.default_days
STOCKBIT_PROFILE_DIR = Path(APP_CFG.storage.stockbit_profile_dir)

# Benchmark ticker always included in every market refresh run (first in list).
# Required by: saham analyze regime, saham analyze swing (market context).
# Also used as ground truth for last IDX trading day (see _last_known_trading_day).
_BENCHMARK_TICKER = BENCHMARK_TICKER

# How many calendar days of gap at the START of a requested range is tolerable
# before triggering a backfill. 7 covers cases where IDX simply has no data
# for the first few days of a very old historical range.
MARKET_START_TOLERANCE_DAYS: int = APP_CFG.fetch.start_tolerance_days


def _last_known_trading_day(db_path: Path) -> date | None:
    """
    Return the latest date in the ^JKSE candle cache.

    Yahoo Finance only includes actual IDX trading sessions, so this date
    is the last known trading day — correctly excluding weekends and IDX
    public holidays without any heuristic or API call.

    Returns None on first run before ^JKSE has been cached.
    """
    repo = SQLiteMarketRepository(db_path=db_path)
    date_range = repo.get_date_range("^JKSE")
    return date_range[1] if date_range else None


def _last_weekday(as_of: date) -> date:
    """
    Fallback: most recent Mon–Fri on or before as_of.
    Used only when ^JKSE candles are not yet cached (first run).
    Does NOT account for IDX holidays — use _last_known_trading_day() when possible.
    """
    if as_of.weekday() == 5:   # Saturday → Friday
        return as_of - timedelta(days=1)
    if as_of.weekday() == 6:   # Sunday → Friday
        return as_of - timedelta(days=2)
    return as_of


def _fmt_status(s: str) -> str:
    """Map internal status strings to concise display labels."""
    for prefix in ("agg=up-to-date(", "daily=up-to-date(", "up-to-date("):
        if s.startswith(prefix):
            tag = prefix[: prefix.index("up-to-date(")]  # "" | "agg=" | "daily="
            date_part = s[len(prefix):-1]
            return f"{tag}✓({date_part})"
    return s


def _clean_row_span(s: str) -> str:
    import re
    # Remove up-to-date prefix
    s = _fmt_status(s)
    # Replace backfill+Nrows/span=Kd -> bf+Nr(Kd)
    s = re.sub(r'backfill\+(\d+)rows/span=(\d+)d', r'bf+\1r(\2d)', s)
    # Replace +Nrows/span=Kd -> +Nr(Kd)
    s = re.sub(r'\+(\d+)rows/span=(\d+)d', r'+\1r(\2d)', s)
    # Replace refreshed/span=Kd -> ref(Kd)
    s = re.sub(r'refreshed/span=(\d+)d', r'ref(\1d)', s)
    return s


def _split_flow_parts(flow_str: str) -> tuple[str, str]:
    import re
    daily_part = "skip"
    agg_part = "skip"

    # Extract daily part
    daily_match = re.search(r'(daily=✓\([^)]+\)|daily=[^ ]+|daily:\+[^ ]+)', flow_str)
    if daily_match:
        daily_part = daily_match.group(1)

    # Extract agg part
    agg_match = re.search(r'(agg=✓\([^)]+\)|agg=[^ ]+|agg:\+[^ ]+)', flow_str)
    if agg_match:
        agg_part = agg_match.group(1)

    # If it's a fallback single status (e.g. no daily or agg keys, like "✓(2026-06-19)" or "skip" or "ERR:...")
    if not daily_match and not agg_match:
        if "ERR:" in flow_str:
            return flow_str, flow_str
        return flow_str, flow_str

    return daily_part, agg_part


def _fmt_tracked_flow_column(daily_part: str) -> str:
    import re
    s = _fmt_status(daily_part)
    s = re.sub(r'\b\d{4}-', '', s)
    s = re.sub(r'daily=✓\(([^)]+)\)', r'✓(\1)', s)
    s = re.sub(r'daily=✓', '✓', s)
    s = re.sub(r'daily:\+(\d+)rows/\d+codes/(\d+)d', r'+\1r(\2d)', s)
    s = re.sub(r'daily:\+(\d+)rows/(\d+)d', r'+\1r(\2d)', s)
    s = re.sub(r'daily:', '', s)
    return s


def _fmt_inst_flow_column(agg_part: str) -> str:
    import re
    s = _fmt_status(agg_part)
    s = re.sub(r'\b\d{4}-', '', s)
    s = re.sub(r'agg=✓\(([^)]+)\)', r'✓(\1)', s)
    s = re.sub(r'agg=✓', '✓', s)
    s = re.sub(r'agg:\+(\d+)rows/(\d+)d', r'+\1r(\2d)', s)
    s = re.sub(r'agg:', '', s)
    return s





def _fmt_meta_column(s: str) -> str:
    # E.g. "new(Financial Services)" or "cached(5d)" or "skip"
    if len(s) <= 18:
        return s

    import re
    match = re.match(r'(\w+)\((.+)\)', s)
    if match:
        prefix, content = match.groups()
        # Truncate content so total length is 18
        max_content_len = 18 - len(prefix) - 2  # -2 for "(" and ")"
        if max_content_len > 3:
            truncated = content[:max_content_len-2] + ".."
            return f"{prefix}({truncated})"
    return s[:18]


def _fmt_enrichment_column(s: str) -> str:
    # E.g. "✓(notation,analyst,insider,season,corp,holding,bandar,fundam,fwd_est,profile)"
    # or "notation+analyst  ✓(insider,season,corp,holding,bandar,fundam,fwd_est,profile)"
    # or "ERR:insider:Playwright error,corp:timeout"
    # or "skip"
    if s == "skip":
        return "skip"

    if s.startswith("ERR:"):
        errors_part = s[4:]
        err_tokens = errors_part.split(",")
        err_labels = []
        for token in err_tokens:
            parts = token.split(":")
            if parts:
                err_labels.append(parts[0])
        failed_count = len(err_labels)
        success_count = max(0, 10 - failed_count)
        return f"{success_count}/10 (ERR: {', '.join(err_labels)})"

    fetched_part = ""
    cached_part = ""

    if "  ✓(" in s:
        parts = s.split("  ✓(")
        fetched_part = parts[0].strip()
        cached_part = parts[1].rstrip(")")
    elif s.startswith("✓("):
        cached_part = s[2:].rstrip(")")
    else:
        fetched_part = s.strip()

    fetched_list = [x for x in fetched_part.split("+") if x]
    cached_list = [x for x in cached_part.split(",") if x]

    fetched_count = len(fetched_list)
    cached_count = len(cached_list)
    total_count = fetched_count + cached_count

    if total_count == 0:
        return s

    if fetched_count == 0:
        return f"{total_count}/{total_count} ✓"

    if fetched_count <= 2:
        return f"{total_count}/{total_count} (+{fetched_count}: {', '.join(fetched_list)})"
    return f"{total_count}/{total_count} (+{fetched_count})"


def _cached_status(latest: date, end_date: date) -> str:
    """Return an explicit cache status for update output."""
    lag_days = (end_date - latest).days
    if lag_days <= 0:
        return f"✓({latest})"
    return f"cached({lag_days}d lag)"


def _no_new_data_status(latest: date | None) -> str:
    if latest is None:
        return "no-data"
    return f"up-to-date({latest.isoformat()})"


def _is_cached_status(status: str) -> bool:
    return status.startswith("✓(")


def _broker_update_status(
    added_count: int,
    updated_range: tuple[date, date] | None,
    fetch_modes: set[str],
) -> str:
    """Return an explicit broker update status for update output."""
    if added_count == 0 and updated_range is None:
        return "no-data"

    span_days = (
        (updated_range[1] - updated_range[0]).days + 1
        if updated_range
        else 0
    )
    prefix = "backfill+" if "backfill" in fetch_modes else "+"
    return f"{prefix}{added_count}rows/span={span_days}d"


def _range_update_status(
    added_count: int,
    updated_range: tuple[date, date] | None,
    fetch_modes: set[str],
) -> str:
    """Return an explicit cache update status for date-ranged data."""
    if added_count == 0 and updated_range is None:
        return "no-data"

    span_days = (
        (updated_range[1] - updated_range[0]).days + 1
        if updated_range
        else 0
    )
    prefix = "backfill+" if "backfill" in fetch_modes else "+"
    return f"{prefix}{added_count}rows/span={span_days}d"


def _echo_note_group(
    title: str,
    messages: list[str],
    color: str,
    limit: int = 12,
    footer: str | None = None,
) -> None:
    """Print a compact note group without flooding large universe updates."""
    if not messages:
        return
    typer.echo("")
    typer.echo(typer.style(title, fg=color))
    for msg in messages[:limit]:
        typer.echo(typer.style(msg, fg=color))
    remaining = len(messages) - limit
    if remaining > 0:
        typer.echo(typer.style(f"  ... {remaining} more", fg=color))
    if footer:
        typer.echo(typer.style(footer, fg=color))


def _create_broker_provider(name: str | None):
    """
    Create broker provider by explicit name, or auto-detect if name is None.

    The returned provider is used for broker_daily_flow, foreign_flow_points, and optionally
    broker_summaries. Summary source is controlled by preferences.broker_summary_source in
    config/stockbit.yaml (default: idx). Stockbit is valid since it now uses
    /company-price-feed/historical/summary for true total_value.

    Auto-detect order:
      1. Playwright session (.stockbit_profile/) — preferred; no token file needed
      2. IDX public API — always available fallback
    """
    if name == "stockbit":
        from src.infrastructure.browser.playwright_stockbit_provider import StockbitPlaywrightBrokerProvider
        return StockbitPlaywrightBrokerProvider(), "stockbit"
    if name == "idx":
        return IdxBrokerDataProvider(), "idx"
    if name is not None:
        raise ValueError(
            "Unknown broker provider: "
            f"{name}. Choose from: idx, stockbit"
        )

    # Auto-detect
    if STOCKBIT_PROFILE_DIR.exists():
        from src.infrastructure.browser.playwright_stockbit_provider import StockbitPlaywrightBrokerProvider
        provider = StockbitPlaywrightBrokerProvider()
        if provider.is_authenticated():
            return provider, "stockbit"
    return IdxBrokerDataProvider(), "idx"


def _fetch_candles(
    ticker: str,
    days: int,
    db_path: Path,
    provider_name: str,
    refresh: bool,
    short_history: list[str] | None = None,
    broker_provider: "StockbitPlaywrightBrokerProvider | None" = None,
) -> str:
    """Fetch candles for one ticker. Returns status string."""
    from src.infrastructure.data_providers.idx_market import IdxMarketDataProvider

    if provider_name == "idx":
        provider = IdxMarketDataProvider()
    elif broker_provider is not None:
        provider = FallbackMarketDataProvider(
            primary=YahooFinanceProvider(),
            fallback=StockbitHistoricalProvider(broker_provider=broker_provider),
        )
    else:
        provider = YahooFinanceProvider()

    repo = SQLiteMarketRepository(db_path=db_path)
    use_case = RefreshMarketDataUseCase(provider=provider, repository=repo)

    try:
        # End tolerance: how many calendar days old can cached data be and still
        # be considered current? Derived from the last known IDX trading day
        # (^JKSE candles). For the benchmark itself, use weekday fallback to
        # break the circular dependency (^JKSE can't use its own stale data
        # to decide if it needs updating).
        today = date.today()
        if ticker.upper() == _BENCHMARK_TICKER:
            last_trading = _last_weekday(today)
        else:
            last_trading = _last_known_trading_day(db_path) or _last_weekday(today)
        end_tolerance = max(0, (today - last_trading).days)

        response = use_case.execute(
            RefreshMarketDataRequest(
                ticker=ticker,
                days=days,
                refresh=refresh,
                start_tolerance_days=MARKET_START_TOLERANCE_DAYS,
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


def _fetch_broker(
    ticker: str,
    days: int,
    db_path: Path,
    broker_provider,
    refresh: bool,
    short_history: list[str] | None = None,
    _idx_summary_provider=None,  # injectable for testing; production code uses IdxBrokerDataProvider
) -> BrokerFetchResult:
    """Fetch broker flow for one ticker. Returns split status for summaries and flow tables."""
    if ticker.startswith("^"):
        return BrokerFetchResult(summaries="n/a:index", flow="n/a:index")

    end_date = date.today()
    repo = SQLiteBrokerRepository(db_path)
    if _idx_summary_provider is not None:
        idx_summary_provider = _idx_summary_provider
    elif broker_provider.provider_name == "idx":
        idx_summary_provider = broker_provider
    elif _broker_summary_source() == "stockbit":
        idx_summary_provider = broker_provider  # Stockbit now returns accurate total_value
    else:
        idx_summary_provider = IdxBrokerDataProvider()

    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider

    notation_repo = StockbitTickerNotationProvider(broker_provider=None, db_path=db_path)

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
            last_trading_day=_last_known_trading_day(db_path) or _last_weekday(end_date),
            requested_start_tolerance_days=MARKET_START_TOLERANCE_DAYS,
        )
    )
    if short_history is not None:
        short_history.extend(response.notes)
    return BrokerFetchResult(
        summaries=response.summaries_status,
        flow=response.flow_status,
    )


def _print_table_summary(
    db_path: Path,
    stock_tickers: list[str],
    candles_provider: str,
    broker_provider_name: str,
    no_meta: bool,
    candles_only: bool,
    broker_only: bool,
    enrichment_available: bool = False,
    market_is_open: bool = False,
) -> None:
    """Print a dynamic post-run database status for tables touched by update."""
    try:
        statuses = build_data_update_table_statuses(
            db_path=db_path,
            tickers=stock_tickers,
            candles_provider=candles_provider,
            broker_provider_name=broker_provider_name,
            no_meta=no_meta,
            candles_only=candles_only,
            broker_only=broker_only,
            enrichment_available=enrichment_available,
            expected_trading_day=_last_known_trading_day(db_path) or _last_weekday(date.today()),
            market_is_open=market_is_open,
        )
    except Exception as e:
        typer.echo("")
        typer.echo(typer.style(f"Database status unavailable: {str(e)[:80]}", fg=typer.colors.YELLOW))
        return

    W = 140
    prefix_width = 95
    impact_width = W - prefix_width
    typer.echo(f"\n{'─' * W}")
    typer.echo("  Database status after command (scoped to this run's stock tickers)")
    typer.echo(f"{'─' * W}")
    typer.echo(f"  {'TABLE':<24} {'SOURCE':<16} {'ROWS':>8} {'TICKERS':>7} {'RANGE/FRESH':<23} {'STATUS':<9} IMPACT")
    typer.echo(f"{'─' * W}")

    issues: list[str] = []
    for status in statuses:
        rows = "-" if status.rows is None else f"{status.rows:,}"
        tickers = "-" if status.tickers is None else f"{status.tickers:,}"
        color = typer.colors.GREEN
        if status.status in {"skipped", "n/a"}:
            color = typer.colors.BRIGHT_BLACK
        elif status.status == "pending-eod":
            color = typer.colors.CYAN
        elif status.status in {"partial", "stale", "empty", "missing", "missing-db"}:
            color = typer.colors.YELLOW
        prefix = (
            f"  {status.table:<24} {status.source:<16} {rows:>8} {tickers:>7} "
            f"{status.range_label:<23} {status.status:<9}"
        )
        if len(status.impact) <= impact_width:
            typer.echo(typer.style(f"{prefix} {status.impact}", fg=color))
        else:
            typer.echo(typer.style(prefix, fg=color))
            typer.echo(typer.style(f"  {'':<{prefix_width - 2}}{status.impact}", fg=color))
        if status.issue and status.status != "pending-eod":
            issues.append(f"  {status.table}: {status.issue}")

    typer.echo(f"{'─' * W}")
    typer.echo(f"  Rows/tickers are totals for the {len(stock_tickers)} stock ticker(s) in this run.")
    if issues:
        _echo_note_group(
            title=f"Database issues/impact ({len(issues)}):",
            messages=issues,
            color=typer.colors.YELLOW,
            footer="   Update succeeded unless a fetch error was listed above; incomplete optional caches are warnings.",
        )


def _fetch_enrichment(ticker: str, db_path: Path, broker_provider) -> str:
    """Pre-fetch Stockbit enrichment data for one ticker into SQLite cache.

    Delegates cache-freshness-then-fetch policy to RefreshStockbitEnrichmentUseCase.
    Returns a compact status string, e.g. "analyst+bandar  ✓(insider,season,corp,holding)".
    """
    from src.infrastructure.browser.playwright_stockbit_provider import StockbitPlaywrightBrokerProvider

    if not isinstance(broker_provider, StockbitPlaywrightBrokerProvider):
        return "skip:no-stockbit"
    if ticker.startswith("^"):
        return "n/a:index"

    from datetime import timedelta

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
    from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
    from src.infrastructure.browser.stockbit_earnings import StockbitEarningsProvider
    from src.infrastructure.browser.stockbit_forward_estimates import (
        StockbitForwardEstimatesProvider,
    )
    from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider
    from src.infrastructure.browser.stockbit_ticker_notation import StockbitTickerNotationProvider
    from src.infrastructure.browser.stockbit_valuation import StockbitValuationProvider

    today = date.today()
    insider_from = today - timedelta(days=365)

    analyst_prov = StockbitAnalystConsensusProvider(broker_provider=broker_provider, db_path=db_path)
    insider_prov = StockbitInsiderActivityProvider(broker_provider=broker_provider, db_path=db_path)
    season_prov = StockbitSeasonalityProvider(broker_provider=broker_provider, db_path=db_path)
    corp_repo = StockbitCorporateActionRepository(broker_provider=broker_provider, db_path=db_path)
    shareholding_prov = StockbitShareholdingProvider(broker_provider=broker_provider, db_path=db_path)
    bandar_prov = StockbitBandarDetectorProvider(broker_provider=broker_provider, db_path=db_path)
    fundamentals_prov = StockbitFundamentalsProvider(broker_provider=broker_provider, db_path=db_path)
    notation_prov = StockbitTickerNotationProvider(broker_provider=broker_provider, db_path=db_path)
    fwd_est_prov = StockbitForwardEstimatesProvider(broker_provider=broker_provider, db_path=db_path)
    profile_prov = StockbitCompanyProfileProvider(broker_provider=broker_provider, db_path=db_path)
    earnings_prov = StockbitEarningsProvider(broker_provider=broker_provider, db_path=db_path)
    distribution_prov = StockbitBrokerDistributionProvider(broker_provider=broker_provider, db_path=db_path)
    valuation_prov = StockbitValuationProvider(broker_provider=broker_provider, db_path=db_path)

    tasks = [
        EnrichmentTask("notation", lambda: notation_prov.is_cache_fresh(ticker),   lambda: notation_prov.get_notation(ticker)),
        EnrichmentTask("analyst",  lambda: analyst_prov._is_cache_fresh(ticker),   lambda: analyst_prov.get_consensus(ticker)),
        EnrichmentTask("insider",  lambda: insider_prov._is_cache_fresh(ticker),   lambda: insider_prov.get_insider_transactions(ticker, insider_from, today, "ALL")),
        EnrichmentTask("season",   lambda: season_prov._is_cache_fresh(ticker, today.year, today.month), lambda: season_prov.get_seasonal_edge(ticker, today.year, today.month)),
        EnrichmentTask("corp",     lambda: corp_repo._is_cache_fresh(ticker),      lambda: corp_repo.get_upcoming_events(ticker, today, today + timedelta(days=90))),
        EnrichmentTask("holding",  lambda: shareholding_prov._is_cache_fresh(ticker), lambda: shareholding_prov.get_composition(ticker)),
        EnrichmentTask("bandar",   lambda: bandar_prov._is_cache_fresh(ticker),    lambda: bandar_prov.get_snapshot(ticker)),
        EnrichmentTask("fundam",   lambda: fundamentals_prov._is_cache_fresh(ticker), lambda: fundamentals_prov.get_fundamentals(ticker)),
        EnrichmentTask("fwd_est",  lambda: fwd_est_prov._read_cache(ticker) is not None, lambda: fwd_est_prov.get_forward_estimates(ticker)),
        EnrichmentTask("profile",  lambda: profile_prov._read_cache(ticker) is not None, lambda: profile_prov.get_profile(ticker)),
        EnrichmentTask("earnings", lambda: earnings_prov.is_cache_fresh(ticker),   lambda: earnings_prov.get_earnings_history(ticker)),
        EnrichmentTask("brdist",   lambda: distribution_prov.is_cache_fresh(ticker), lambda: distribution_prov.get_distribution(ticker)),
        EnrichmentTask("valuation", lambda: valuation_prov.is_cache_fresh(ticker),   lambda: valuation_prov.get_valuation(ticker)),
    ]
    return RefreshStockbitEnrichmentUseCase().execute(
        RefreshStockbitEnrichmentRequest(ticker=ticker, tasks=tasks)
    ).status


def _fetch_meta(ticker: str, db_path: Path) -> str:
    """Fetch sector/industry metadata for one ticker. Returns a status string."""
    if ticker.startswith("^"):
        return "n/a:index"

    try:
        repo = SQLiteStockMetaRepository(db_path)
        provider = YahooStockMetaProvider()
        use_case = FetchStockMetaUseCase(provider=provider, repository=repo)
        result = use_case.execute(FetchStockMetaRequest(ticker=ticker))

        if result.status == "cached":
            return f"cached({result.cached_days}d)"
        if result.status == "new":
            return f"new({result.sector or '?'})"
        if result.status == "changed":
            return f"changed→{result.sector or '?'}"
        if result.status == "verified":
            return "verified"
        # error
        return f"ERR:{(result.error or 'unknown')[:30]}"
    except Exception as e:
        return f"ERR:{str(e)[:30]}"


def _fetch_global_context_tickers(db_path: Path, days: int = 180) -> None:
    """
    Fetch MCE global context tickers (^VIX, EIDO, IDR=X, etc.) via Yahoo Finance
    with no market suffix — these are not IDX stocks.

    Called automatically at the end of `saham fetch market` (candles path only).
    Tickers are read from config/market_context_engine.yaml so disabling a factor
    also stops fetching its ticker.
    """
    from src.infrastructure.config.market_context_config import load_market_context_config
    from src.application.use_case.refresh_market_data_use_case import (
        RefreshMarketDataRequest,
        RefreshMarketDataUseCase,
    )

    cfg = load_market_context_config()
    global_tickers: list[tuple[str, str]] = []  # (ticker, factor_name)

    if cfg.vix.enabled:
        global_tickers.append((cfg.vix.ticker, "vix"))
    if cfg.eido.enabled:
        global_tickers.append((cfg.eido.ticker, "eido"))
    if cfg.usd_idr.enabled:
        global_tickers.append((cfg.usd_idr.ticker, "usd_idr"))

    if not global_tickers:
        return

    provider = YahooFinanceProvider(market_suffix="")
    repo = SQLiteMarketRepository(db_path=db_path)
    use_case = RefreshMarketDataUseCase(provider=provider, repository=repo)

    results: list[str] = []
    for ticker, factor in global_tickers:
        try:
            resp = use_case.execute(
                RefreshMarketDataRequest(
                    ticker=ticker,
                    days=days,
                    refresh=False,
                    start_tolerance_days=MARKET_START_TOLERANCE_DAYS,
                    end_tolerance_days=3,   # global markets close at US hours; allow 3d tolerance
                )
            )
            if resp.status.startswith("cached"):
                status = f"✓"
            else:
                status = resp.status
            results.append(f"{ticker}({factor}):{status}")
        except Exception as e:
            results.append(f"{ticker}({factor}):ERR:{str(e)[:20]}")

    typer.echo(f"  Context tickers: {', '.join(results)}")


def fetch_market(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI BMRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe", "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Days of history to fetch", min=1),
    ] = DEFAULT_DAYS,
    candles_only: Annotated[
        bool,
        typer.Option("--candles-only", help="Skip broker flow fetch"),
    ] = False,
    broker_only: Annotated[
        bool,
        typer.Option("--broker-only", help="Skip candles fetch"),
    ] = False,
    candles_provider: Annotated[
        Optional[str],
        typer.Option("--provider", help="Candles provider: yahoo or idx (default from config/data_sources.yaml)"),
    ] = None,
    broker_provider: Annotated[
        Optional[str],
        typer.Option(
            "--broker-provider",
            help="Broker provider: idx or stockbit. Auto-detects if omitted.",
        ),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", "-r", help="Force refresh even if cached"),
    ] = False,
    no_meta: Annotated[
        bool,
        typer.Option("--no-meta", help="Skip sector/industry metadata fetch"),
    ] = False,
    no_enrichment: Annotated[
        bool,
        typer.Option("--no-enrichment", help="Skip Stockbit enrichment fetch (analyst/insider/seasonality/corp)"),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Fetch fresh candles + broker flow + sector metadata for a stock universe.

    Always includes ^JKSE (benchmark) for regime analysis.
    Sector/industry data is fetched via Yahoo Finance and cached for 30 days
    (only re-fetched when stale). Use --no-meta to skip.

    When a Stockbit session is available, also pre-fetches ticker notation/status,
    analyst consensus, insider activity, seasonality, and corporate actions into SQLite so that
    `saham analyze swing` runs without needing Playwright at analysis time.
    Use --no-enrichment to skip this step.

    Examples:
        saham fetch market --universe lq45
        saham fetch market --universe lq45 --days 30
        saham fetch market BBCA BBRI BMRI
        saham fetch market --universe cached --refresh
        saham fetch market --universe lq45 --broker-only
        saham fetch market BBCA --broker-provider stockbit --days 30
        saham fetch market --universe lq45 --no-meta
        saham fetch market BBCA --no-enrichment
    """
    resolved_db = db_path or Path(APP_CFG.storage.db_path)
    candles_provider = candles_provider or _candle_source()

    # Determine broker provider
    try:
        broker_provider, broker_provider_name = _create_broker_provider(broker_provider)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # Resolve tickers first for header printing
    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers to update. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    # Include benchmark first
    without_benchmark = [t for t in ticker_list if t != _BENCHMARK_TICKER]
    full_ticker_list = [_BENCHMARK_TICKER] + without_benchmark

    enrichment_available = (
        not no_enrichment
        and broker_provider_name == "stockbit"
    )

    # Header
    from src.infrastructure.browser.stockbit_market_time import (
        fetch_and_cache_market_status,
        format_market_status_line,
        get_display_market_status,
    )
    # Attempt to query live market status first, updating the local session cache
    _mstatus = fetch_and_cache_market_status() or get_display_market_status()
    typer.echo(f"\n{format_market_status_line(_mstatus)}")
    typer.echo(f"Updating {len(full_ticker_list)} tickers | {days}d history")
    if not broker_only:
        typer.echo(f"  Candles:          {candles_provider}")
    if not candles_only:
        if broker_provider_name == "stockbit":
            typer.echo("  Summaries:        idx  (true daily totals + top 10 brokers list populated via stockbit)")
            typer.echo("  Tracked Flow:     stockbit  (daily activity for 15 tracked brokers)")
            typer.echo("  Inst. Flow:       stockbit  (net flow proxy for 10 institutional desks)")
        else:
            typer.echo("  Summaries:        idx  (true daily totals; top 10 brokers list NOT available without stockbit)")
            typer.echo("  Tracked Flow:     skip  (requires stockbit login)")
            typer.echo("  Inst. Flow:       skip  (requires stockbit login)")
    if not no_meta:
        typer.echo("  Meta:             yahoo  (sector/industry, 30d TTL)")
    if enrichment_available:
        typer.echo("  Enrichment:       stockbit  (notation/analyst/insider/seasonality/corp, daily SQLite cache)")
    typer.echo("  Legend:  ✓(DATE) = up-to-date through DATE  +N = new rows stored  bf+N = backfilled older gap  agg = inst. flow  ERR: = failed")
    typer.echo("")

    # Print table header
    header_line = f"  {'[Index] Ticker':<15}  {'Candles':<13}  {'Summaries':<18}  {'Tracked Flow':<18}  {'Inst. Flow':<18}"
    sep_line    = f"  {'─────── ──────':<15}  {'─────────────':<13}  {'──────────────────':<18}  {'──────────────────':<18}  {'──────────────────':<18}"
    if not no_meta:
        header_line += f"  {'Meta':<18}"
        sep_line    += f"  {'──────────────────':<18}"
    if enrichment_available:
        header_line += f"  {'Enrichment':<26}"
        sep_line    += f"  {'──────────────────────────':<26}"
    typer.echo(header_line)
    typer.echo(sep_line)

    # Progress streaming callback
    def on_ticker_complete(result, index: int, total: int) -> None:
        progress = f"[{index:>3}/{total}]"

        has_critical_error = "ERR:" in result.candles_status or "ERR:" in result.broker_result.summaries or "ERR:" in result.broker_result.flow
        has_enrich_error = "ERR:" in result.enrichment_status

        if has_critical_error:
            status_color = typer.colors.RED
        elif has_enrich_error:
            status_color = typer.colors.YELLOW
        elif result.all_cached:
            status_color = typer.colors.BRIGHT_BLACK
        else:
            status_color = typer.colors.GREEN

        # Format column values
        candles_col = _clean_row_span(result.candles_status)[:13]
        summaries_col = _clean_row_span(result.broker_result.summaries)[:18]

        daily_flow, agg_flow = _split_flow_parts(result.broker_result.flow)
        tracked_col = _fmt_tracked_flow_column(daily_flow)[:18]
        inst_col = _fmt_inst_flow_column(agg_flow)[:18]

        line_parts = [
            f"  {progress:<9} {result.ticker:<5}",
            f"{candles_col:<13}",
            f"{summaries_col:<18}",
            f"{tracked_col:<18}",
            f"{inst_col:<18}"
        ]

        if not no_meta:
            meta_col = _fmt_meta_column(result.meta_status)[:18]
            line_parts.append(f"{meta_col:<18}")
        if enrichment_available:
            enrich_col = _fmt_enrichment_column(result.enrichment_status)[:26]
            line_parts.append(f"{enrich_col:<26}")

        status_line = "  ".join(line_parts)
        typer.echo(typer.style(status_line, fg=status_color))

    _candles_fn = (
        functools.partial(_fetch_candles, broker_provider=broker_provider)
        if broker_provider_name == "stockbit"
        else _fetch_candles
    )
    use_case = FetchMarketRefreshUseCase(
        fetch_candles=_candles_fn,
        fetch_broker=_fetch_broker,
        fetch_meta=_fetch_meta,
        fetch_enrichment=_fetch_enrichment,
    )
    try:
        response = use_case.execute(
            FetchMarketRefreshRequest(
                tickers=list(tickers) if tickers else [],
                universe=universe,
                days=days,
                db_path=resolved_db,
                candles_provider=candles_provider,
                broker_provider=broker_provider,
                broker_provider_name=broker_provider_name,
                refresh=refresh,
                candles_only=candles_only,
                broker_only=broker_only,
                no_meta=no_meta,
                no_enrichment=no_enrichment,
            ),
            on_ticker_complete=on_ticker_complete,
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # Summary
    typer.echo("")
    typer.echo("=" * 50)
    typer.echo(
        f"Done: {response.ok_count} ok"
        + (f", {response.fail_count} failed" if response.fail_count else "")
    )
    if response.failures:
        typer.echo(f"Failed: {', '.join(response.failures)}")
    _echo_note_group(
        title=(
            f"⚠  Candle cache shorter than --days {days} for "
            f"{len(response.candle_short_history)} ticker(s); "
            "older candle gaps were fetched automatically:"
        ),
        messages=response.candle_short_history,
        color=typer.colors.YELLOW,
        footer="   Use --refresh only when you want to re-fetch the full requested candle window.",
    )
    _echo_note_group(
        title=(
            f"Broker history shorter than --days {days} for "
            f"{len(response.broker_backfills)} ticker(s); older broker gaps were fetched automatically:"
        )
        if response.broker_backfills
        else "",
        messages=response.broker_backfills,
        color=typer.colors.CYAN,
    )
    _echo_note_group(
        title=(
            f"Sector classification changed for {len(response.meta_changed)} ticker(s):"
            if response.meta_changed
            else ""
        ),
        messages=response.meta_changed,
        color=typer.colors.YELLOW,
    )

    # Table summary — exclude index tickers (^JKSE) since they have no broker/meta rows
    _print_table_summary(
        db_path=resolved_db,
        stock_tickers=response.stock_tickers_only,
        candles_provider=candles_provider,
        broker_provider_name=broker_provider_name,
        no_meta=no_meta,
        candles_only=candles_only,
        broker_only=broker_only,
        enrichment_available=response.enrichment_available,
        market_is_open=_mstatus.is_open if _mstatus else False,
    )

    # Fetch MCE global context tickers (VIX, EIDO, USD/IDR) using no-suffix Yahoo provider
    if not broker_only:
        _fetch_global_context_tickers(resolved_db, days=days)
