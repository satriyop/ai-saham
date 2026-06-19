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

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.universe_loader import (
    UniverseNotFoundError,
)
from src.application.use_case.fetch_market_refresh import (
    BENCHMARK_TICKER,
    BrokerFetchResult,
    FetchMarketRefreshRequest,
    FetchMarketRefreshUseCase,
)
from src.application.use_case.fetch_stock_meta import (
    FetchStockMetaRequest,
    FetchStockMetaUseCase,
)
from src.application.use_case.refresh_broker_data import (
    RefreshBrokerDataRequest,
    RefreshBrokerDataUseCase,
)
from src.application.use_case.refresh_market_data import (
    RefreshMarketDataRequest,
    RefreshMarketDataUseCase,
)
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider
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

DEFAULT_DB_PATH = Path("data.db")
DEFAULT_DAYS = 90
STOCKBIT_PROFILE_DIR = Path(".stockbit_profile")

# Benchmark ticker always included in every market refresh run (first in list).
# Required by: saham analyze regime, saham analyze swing (market context).
# Also used as ground truth for last IDX trading day (see _last_known_trading_day).
_BENCHMARK_TICKER = BENCHMARK_TICKER

# How many calendar days of gap at the START of a requested range is tolerable
# before triggering a backfill. 7 covers cases where IDX simply has no data
# for the first few days of a very old historical range.
MARKET_START_TOLERANCE_DAYS = 7


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
    if s.startswith("up-to-date("):
        # e.g. "up-to-date(2026-06-13)" → "✓(2026-06-13)"
        date_part = s[len("up-to-date("):-1]
        return f"✓({date_part})"
    return s


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

    The returned provider is used ONLY for broker_daily_flow and foreign_flow_points.
    broker_summaries always go through IdxBrokerDataProvider (accurate total_value).

    Auto-detect order:
      1. Playwright session (.stockbit_profile/) — preferred; no token file needed
      2. IDX public API — always available fallback
    """
    if name == "stockbit-session":
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        return StockbitPlaywrightBrokerProvider(), "stockbit-session"
    if name == "idx":
        return IdxBrokerDataProvider(), "idx"
    if name is not None:
        raise ValueError(
            "Unknown broker provider: "
            f"{name}. Choose from: idx, stockbit-session"
        )

    # Auto-detect
    if STOCKBIT_PROFILE_DIR.exists():
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        provider = StockbitPlaywrightBrokerProvider()
        if provider.is_authenticated():
            return provider, "stockbit-session"
    return IdxBrokerDataProvider(), "idx"


def _fetch_candles(
    ticker: str,
    days: int,
    db_path: Path,
    provider_name: str,
    refresh: bool,
    short_history: list[str] | None = None,
) -> str:
    """Fetch candles for one ticker. Returns status string."""
    from src.infrastructure.data_providers.idx_market import IdxMarketDataProvider

    if provider_name == "idx":
        provider = IdxMarketDataProvider()
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
    else:
        idx_summary_provider = IdxBrokerDataProvider()

    response = RefreshBrokerDataUseCase(
        broker_provider=broker_provider,
        idx_summary_provider=idx_summary_provider,
        repository=repo,
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
        )
    except Exception as e:
        typer.echo("")
        typer.echo(typer.style(f"Database status unavailable: {str(e)[:80]}", fg=typer.colors.YELLOW))
        return

    W = 112
    prefix_width = 91
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
        if status.issue:
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

    Fetches analyst consensus, insider activity (last 365 days ALL actions),
    monthly seasonality, corporate actions, shareholding composition, bandar
    detector signal, and fundamental ratios (KeyStats). Each provider checks
    its own SQLite cache and skips the API call if data is already fresh.

    Returns a compact status string, e.g. "analyst+bandar+fundam  ✓(insider,season,corp,holding)"
    on partial cache hit, or "✓(all)" if all providers had fresh data, or
    "skip" if provider is unavailable.
    """
    from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider

    if not isinstance(broker_provider, StockbitPlaywrightBrokerProvider):
        return "skip:no-stockbit"
    if ticker.startswith("^"):
        return "n/a:index"

    from datetime import timedelta

    from src.infrastructure.browser.stockbit_analyst import StockbitAnalystConsensusProvider
    from src.infrastructure.browser.stockbit_bandar import StockbitBandarDetectorProvider
    from src.infrastructure.browser.stockbit_corp_action import StockbitCorporateActionRepository
    from src.infrastructure.browser.stockbit_fundamentals import StockbitFundamentalsProvider
    from src.infrastructure.browser.stockbit_insider import StockbitInsiderActivityProvider
    from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
    from src.infrastructure.browser.stockbit_shareholding import StockbitShareholdingProvider

    today = date.today()
    insider_from = today - timedelta(days=365)

    analyst_prov = StockbitAnalystConsensusProvider(broker_provider=broker_provider, db_path=db_path)
    insider_prov = StockbitInsiderActivityProvider(broker_provider=broker_provider, db_path=db_path)
    season_prov = StockbitSeasonalityProvider(broker_provider=broker_provider, db_path=db_path)
    corp_repo = StockbitCorporateActionRepository(broker_provider=broker_provider, db_path=db_path)
    shareholding_prov = StockbitShareholdingProvider(broker_provider=broker_provider, db_path=db_path)
    bandar_prov = StockbitBandarDetectorProvider(broker_provider=broker_provider, db_path=db_path)
    fundamentals_prov = StockbitFundamentalsProvider(broker_provider=broker_provider, db_path=db_path)

    fetched: list[str] = []
    cached: list[str] = []
    errors: list[str] = []

    def _run(label: str, fn):
        try:
            fn()
            return True
        except Exception as e:
            errors.append(f"{label}:{str(e)[:20]}")
            return False

    # Analyst consensus
    if analyst_prov._is_cache_fresh(ticker):
        cached.append("analyst")
    elif _run("analyst", lambda: analyst_prov.get_consensus(ticker)):
        fetched.append("analyst")

    # Insider (fetch ALL actions for last 365 days so swing analyze hits cache regardless of range)
    if insider_prov._is_cache_fresh(ticker):
        cached.append("insider")
    elif _run("insider", lambda: insider_prov.get_insider_transactions(ticker, insider_from, today, "ALL")):
        fetched.append("insider")

    # Seasonality for current month
    if season_prov._is_cache_fresh(ticker, today.year, today.month):
        cached.append("season")
    elif _run("season", lambda: season_prov.get_seasonal_edge(ticker, today.year, today.month)):
        fetched.append("season")

    # Corp actions for the next 90 days
    if corp_repo._is_cache_fresh(ticker):
        cached.append("corp")
    elif _run("corp", lambda: corp_repo.get_upcoming_events(ticker, today, today + timedelta(days=90))):
        fetched.append("corp")

    # Shareholding composition (7-day TTL — quarterly filings)
    if shareholding_prov._is_cache_fresh(ticker):
        cached.append("holding")
    elif _run("holding", lambda: shareholding_prov.get_composition(ticker)):
        fetched.append("holding")

    # Bandar detector (daily — fixed after session close)
    if bandar_prov._is_cache_fresh(ticker):
        cached.append("bandar")
    elif _run("bandar", lambda: bandar_prov.get_snapshot(ticker)):
        fetched.append("bandar")

    # Fundamentals / KeyStats (7-day TTL — quarterly metrics)
    if fundamentals_prov._is_cache_fresh(ticker):
        cached.append("fundam")
    elif _run("fundam", lambda: fundamentals_prov.get_fundamentals(ticker)):
        fetched.append("fundam")

    if errors:
        return "ERR:" + ",".join(errors)
    if not fetched:
        return f"✓({','.join(cached)})"
    return "+".join(fetched) + (f"  ✓({','.join(cached)})" if cached else "")


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
        str,
        typer.Option("--provider", help="Candles provider: yahoo or idx"),
    ] = "yahoo",
    broker_provider: Annotated[
        Optional[str],
        typer.Option(
            "--broker-provider",
            help="Broker provider: idx or stockbit-session. Auto-detects if omitted.",
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

    When a Stockbit session is available, also pre-fetches analyst consensus,
    insider activity, seasonality, and corporate actions into SQLite so that
    `saham analyze swing` runs without needing Playwright at analysis time.
    Use --no-enrichment to skip this step.

    Examples:
        saham fetch market --universe lq45
        saham fetch market --universe lq45 --days 30
        saham fetch market BBCA BBRI BMRI
        saham fetch market --universe cached --refresh
        saham fetch market --universe lq45 --broker-only
        saham fetch market BBCA --broker-provider stockbit-session --days 30
        saham fetch market --universe lq45 --no-meta
        saham fetch market BBCA --no-enrichment
    """
    resolved_db = db_path or DEFAULT_DB_PATH

    # Determine broker provider
    try:
        broker_provider, broker_provider_name = _create_broker_provider(broker_provider)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    use_case = FetchMarketRefreshUseCase(
        fetch_candles=_fetch_candles,
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
            )
        )
    except UniverseNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not response.ticker_list:
        typer.echo(
            "No tickers to update. Specify --universe or provide ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    # Header
    from src.infrastructure.browser.stockbit_market_time import (
        format_market_status_line,
        get_display_market_status,
    )
    _mstatus = get_display_market_status()
    typer.echo(f"\n{format_market_status_line(_mstatus)}")
    typer.echo(f"Updating {len(response.ticker_list)} tickers | {days}d history")
    if not broker_only:
        typer.echo(f"  Candles:          {candles_provider}")
    if not candles_only:
        # broker_summaries always route to IDX regardless of the selected provider;
        # flow tables (foreign_flow_points, broker_daily_flow) use the chosen provider.
        typer.echo("  Broker summaries: idx  (foreign totals + named brokers)")
        typer.echo(f"  Broker flow:      {broker_provider_name}  (net flow timeseries + daily named breakdown)")
    if not no_meta:
        typer.echo("  Meta:             yahoo  (sector/industry, 30d TTL)")
    if response.enrichment_available:
        typer.echo("  Enrichment:       stockbit  (analyst/insider/seasonality/corp, daily SQLite cache)")
    typer.echo("  Legend:  ✓(DATE) = up-to-date through DATE  +N = new rows stored  ERR: = failed")
    typer.echo("")

    for i, result in enumerate(response.ticker_results, 1):
        progress = f"[{i:>3}/{len(response.ticker_list)}]"
        status_color = typer.colors.RED
        if not result.any_error:
            status_color = (
                typer.colors.BRIGHT_BLACK
                if result.all_cached
                else typer.colors.GREEN
            )

        status_line = (
            f"candles={_fmt_status(result.candles_status)}"
            f"  summ={_fmt_status(result.broker_result.summaries)}"
            f"  flow={_fmt_status(result.broker_result.flow)}"
        )
        if not no_meta:
            status_line += f"  meta={result.meta_status}"
        if response.enrichment_available:
            status_line += f"  enrich={result.enrichment_status}"

        typer.echo(
            f"  {progress} {result.ticker:<6} "
            + typer.style(status_line, fg=status_color)
        )

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
    )
