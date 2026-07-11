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
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.fetch_market_broker_refresh import fetch_broker
from src.adapters.cli.fetch_market_candle_refresh import fetch_candles
from src.adapters.cli.fetch_market_context_inputs import refresh_market_context_inputs
from src.adapters.cli.fetch_market_display import (
    clean_row_span,
    echo_note_group,
    fmt_enrichment_column,
    fmt_inst_flow_column,
    fmt_meta_column,
    fmt_tracked_flow_column,
    print_table_summary,
    render_enrichment_pit_coverage,
    split_flow_parts,
)
from src.adapters.cli.fetch_market_enrichment_refresh import (
    fetch_enrichment,
    read_enrichment_pit_coverage,
)
from src.adapters.cli.fetch_market_meta_refresh import fetch_meta
from src.adapters.cli.fetch_market_provider_factory import create_broker_provider
from src.application.services.market_freshness_service import (
    BenchmarkTickerAliases,
    MarketFreshnessService,
)
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.fetch_market_refresh_use_case import (
    BENCHMARK_TICKER,
    FetchMarketRefreshRequest,
    FetchMarketRefreshUseCase,
)
from src.application.use_case.resolve_candle_provider_policy_use_case import (
    ResolveCandleProviderPolicyRequest,
    ResolveCandleProviderPolicyUseCase,
)
from src.domain.value_objects.benchmark_symbol import YAHOO_IHSG_TICKER, canonicalize_ticker
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.data_sources_config import (
    candle_source as _candle_source,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

DEFAULT_DAYS: int = APP_CFG.fetch.default_days
STOCKBIT_PROFILE_DIR = Path(APP_CFG.storage.stockbit_profile_dir)

# Benchmark ticker always included in every market refresh run (first in list).
# Required by: saham analyze regime, saham analyze swing (market context).
_BENCHMARK_TICKER = BENCHMARK_TICKER
_BENCHMARK_ALIASES = BenchmarkTickerAliases(canonical=_BENCHMARK_TICKER, legacy=YAHOO_IHSG_TICKER)


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


def _find_missing_stockbit_session_error(
    tickers: list[str],
    non_idx_tickers: frozenset[str],
    candles_provider: str,
    has_broker_session: bool,
) -> str | None:
    """
    Return the candle-provider policy error message if any ticker in the batch
    would fail provider resolution (regular IDX ticker, provider != idx, no
    Stockbit session), or None if the batch is fetchable as-is.

    This is a command precondition, not a per-ticker transient fetch failure:
    every affected ticker would fail identically, so the command must fail
    fast before starting the ticker loop instead of surfacing a raw exception
    mid-run.
    """
    policy_use_case = ResolveCandleProviderPolicyUseCase()
    for ticker in tickers:
        decision = policy_use_case.execute(
            ResolveCandleProviderPolicyRequest(
                ticker=ticker,
                non_idx_tickers=non_idx_tickers,
                requested_provider_name=candles_provider,
                has_broker_session=has_broker_session,
            )
        )
        if decision.error is not None:
            return decision.error
    return None


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
    no_calendar: Annotated[
        bool,
        typer.Option("--no-calendar", help="Skip market-wide corporate action calendar sync"),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Fetch fresh candles + broker flow + sector metadata for a stock universe.

    Always includes IHSG (benchmark) for regime analysis.
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
        broker_provider, broker_provider_name = create_broker_provider(broker_provider)
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

    # Include benchmark first for display. The use case repeats this canonical
    # normalization for execution.
    without_benchmark = [
        canonicalize_ticker(t) for t in ticker_list
        if canonicalize_ticker(t) != _BENCHMARK_TICKER
    ]
    full_ticker_list = [_BENCHMARK_TICKER] + list(dict.fromkeys(without_benchmark))

    # Fail fast on a command precondition: if candles will be fetched and any
    # ticker in the batch requires a Stockbit session that is not available,
    # abort before starting the per-ticker loop instead of letting the
    # resulting ValueError surface uncaught mid-run.
    if not broker_only:
        from src.infrastructure.config.market_context_config import get_global_context_tickers

        precondition_error = _find_missing_stockbit_session_error(
            tickers=full_ticker_list,
            non_idx_tickers=frozenset(get_global_context_tickers()),
            candles_provider=candles_provider,
            # Matches the real ticker-loop signal below: fetch_candles only
            # receives a broker_provider (enabling Stockbit-backed fetches)
            # when broker_provider_name == "stockbit"; create_broker_provider
            # always returns a non-None object even for the IDX fallback, so
            # `broker_provider is not None` would never detect a missing
            # session here.
            has_broker_session=broker_provider_name == "stockbit",
        )
        if precondition_error is not None:
            typer.echo(f"Error: {precondition_error}", err=True)
            raise typer.Exit(1)

    enrichment_available = (
        not no_enrichment
        and broker_provider_name == "stockbit"
    )

    # Flag-routing for the market-wide calendar sync (pure flag combination — no
    # fetch/freshness policy here). The actual fetch happens once after the
    # per-ticker loop; skip statuses are decided by flags alone.
    calendar_skip_status: str | None
    if no_calendar:
        calendar_skip_status = "skip:--no-calendar"
    elif no_enrichment:
        calendar_skip_status = "skip:--no-enrichment"
    elif broker_provider_name != "stockbit":
        calendar_skip_status = "skip:no-stockbit"
    else:
        calendar_skip_status = None

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
        candles_col = clean_row_span(result.candles_status)[:13]
        summaries_col = clean_row_span(result.broker_result.summaries)[:18]

        daily_flow, agg_flow = split_flow_parts(result.broker_result.flow)
        tracked_col = fmt_tracked_flow_column(daily_flow)[:18]
        inst_col = fmt_inst_flow_column(agg_flow)[:18]

        line_parts = [
            f"  {progress:<9} {result.ticker:<5}",
            f"{candles_col:<13}",
            f"{summaries_col:<18}",
            f"{tracked_col:<18}",
            f"{inst_col:<18}"
        ]

        if not no_meta:
            meta_col = fmt_meta_column(result.meta_status)[:18]
            line_parts.append(f"{meta_col:<18}")
        if enrichment_available:
            enrich_col = fmt_enrichment_column(result.enrichment_status)[:26]
            line_parts.append(f"{enrich_col:<26}")

        status_line = "  ".join(line_parts)
        typer.echo(typer.style(status_line, fg=status_color))

    _candles_fn = (
        functools.partial(fetch_candles, broker_provider=broker_provider)
        if broker_provider_name == "stockbit"
        else fetch_candles
    )
    _read_coverage_fn = (
        functools.partial(read_enrichment_pit_coverage, resolved_db)
        if enrichment_available
        else None
    )
    use_case = FetchMarketRefreshUseCase(
        fetch_candles=_candles_fn,
        fetch_broker=fetch_broker,
        fetch_meta=fetch_meta,
        fetch_enrichment=fetch_enrichment,
        read_pit_coverage=_read_coverage_fn,
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

    # Market-wide corporate action calendar — synced ONCE per command run,
    # never per ticker. Skip statuses are pure flag routing decided above;
    # the actual fetch/freshness policy lives inside the use case.
    if calendar_skip_status is not None:
        calendar_status = calendar_skip_status
    else:
        from src.adapters.cli.fetch_market_calendar_refresh import refresh_market_calendar

        calendar_status = refresh_market_calendar(
            db_path=resolved_db,
            api_client=broker_provider.api_client,
            refresh=refresh,
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
    echo_note_group(
        title=(
            f"⚠  Candle cache shorter than --days {days} for "
            f"{len(response.candle_short_history)} ticker(s); "
            "older candle gaps were fetched automatically:"
        ),
        messages=response.candle_short_history,
        color=typer.colors.YELLOW,
        footer="   Use --refresh only when you want to re-fetch the full requested candle window.",
    )
    echo_note_group(
        title=(
            f"Broker history shorter than --days {days} for "
            f"{len(response.broker_backfills)} ticker(s); older broker gaps were fetched automatically:"
        )
        if response.broker_backfills
        else "",
        messages=response.broker_backfills,
        color=typer.colors.CYAN,
    )
    echo_note_group(
        title=(
            f"Sector classification changed for {len(response.meta_changed)} ticker(s):"
            if response.meta_changed
            else ""
        ),
        messages=response.meta_changed,
        color=typer.colors.YELLOW,
    )

    # Table summary — exclude index tickers since they have no broker/meta rows
    print_table_summary(
        db_path=resolved_db,
        stock_tickers=response.stock_tickers_only,
        candles_provider=candles_provider,
        broker_provider_name=broker_provider_name,
        no_meta=no_meta,
        candles_only=candles_only,
        broker_only=broker_only,
        expected_trading_day=MarketFreshnessService(
            repository=SQLiteMarketRepository(db_path=resolved_db)
        ).resolve_reference_trading_day(_BENCHMARK_ALIASES, date.today()),
        enrichment_available=response.enrichment_available,
        market_is_open=_mstatus.is_open if _mstatus else False,
    )

    typer.echo(f"Calendar: {calendar_status}")

    if response.pit_coverage:
        render_enrichment_pit_coverage(response.pit_coverage)

    # Fetch MCE global context tickers (VIX, EIDO, USD/IDR) using no-suffix Yahoo provider
    if not broker_only:
        context_response = refresh_market_context_inputs(resolved_db, days=days)
        if context_response.statuses:
            typer.echo(f"  Context tickers: {', '.join(context_response.statuses)}")
