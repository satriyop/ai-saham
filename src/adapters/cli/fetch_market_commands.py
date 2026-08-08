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

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.cli_errors import (
    raise_data_unavailable,
    raise_user_error,
    resolve_cli_db_path,
)
from src.adapters.cli.fetch_market_display import (
    echo_note_group,
    fetch_market_row_color,
    print_table_summary,
    render_enrichment_pit_coverage,
    render_fetch_market_row,
)
from src.adapters.cli.fetch_market_provider_factory import create_broker_provider
from src.application.services.universe_loader import UniverseNotFoundError
from src.application.use_case.fetch_market_command_workflow_use_case import (
    FetchMarketCommandStartEvent,
    FetchMarketCommandWorkflowRequest,
)
from src.application.use_case.fetch_market_refresh_use_case import FetchMarketTickerResult
from src.infrastructure.composition.fetch_market.fetch_market_workflow_factory import (
    create_workflow_use_case,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.data_sources_config import (
    candle_source as _candle_source,
)


def fetch_market(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI BMRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    days: Annotated[
        Optional[int],
        typer.Option("--days", "-d", help="Days of history to fetch", min=1),
    ] = None,
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
        typer.Option(
            "--provider",
            help="Candles provider: yahoo or idx (default from config/data_sources.yaml)",
        ),
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
        typer.Option(
            "--no-enrichment",
            help="Skip Stockbit enrichment fetch (analyst/insider/seasonality/corp)",
        ),
    ] = False,
    no_calendar: Annotated[
        bool,
        typer.Option("--no-calendar", help="Skip market-wide corporate action calendar sync"),
    ] = False,
    no_macro_calendar: Annotated[
        bool,
        typer.Option(
            "--no-macro-calendar",
            help="Skip market-wide macro economic calendar sync (BI rate, CPI, etc.)",
        ),
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
    `saham plan swing` runs without needing Playwright at analysis time.
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
    cfg = load_app_config()
    resolved_days = days if days is not None else cfg.fetch.default_days
    resolved_db = resolve_cli_db_path(db_path, configured_default=cfg.storage.db_path)
    candles_provider = candles_provider or _candle_source()

    # Determine broker provider
    try:
        broker_provider_obj, broker_provider_name = create_broker_provider(broker_provider)
    except ValueError as e:
        # Session-required / unknown provider are operator-actionable input/env.
        msg = str(e)
        if "session" in msg.lower() or "login" in msg.lower() or "auth" in msg.lower():
            raise_data_unavailable(msg, tip="Run: saham fetch stockbit login")
        raise_user_error(msg)

    # Build the workflow use case via factory
    workflow_use_case = create_workflow_use_case(
        db_path=resolved_db,
        broker_provider=broker_provider_obj,
        broker_provider_name=broker_provider_name,
    )

    def on_start(event: FetchMarketCommandStartEvent) -> None:
        if event.market_status_line:
            typer.echo(f"\n{event.market_status_line}")
        typer.echo(f"Updating {event.ticker_count} tickers | {resolved_days}d history")
        if not event.broker_only:
            typer.echo(f"  Candles:          {event.candles_provider}")
        if not event.candles_only:
            if event.broker_provider_name == "stockbit":
                typer.echo(
                    "  Summaries:        idx  (true daily totals + top 10 brokers list"
                    " populated via stockbit)"
                )
                typer.echo("  Tracked Flow:     stockbit  (daily activity for 15 tracked brokers)")
                typer.echo(
                    "  Inst. Flow:       stockbit  (net flow proxy for 10 institutional desks)"
                )
            else:
                typer.echo(
                    "  Summaries:        idx  (true daily totals; top 10 brokers list"
                    " NOT available without stockbit)"
                )
                typer.echo("  Tracked Flow:     skip  (requires stockbit login)")
                typer.echo("  Inst. Flow:       skip  (requires stockbit login)")
        if not event.no_meta:
            typer.echo("  Meta:             yahoo  (sector/industry, 30d TTL)")
        if event.enrichment_available:
            typer.echo(
                "  Enrichment:       stockbit  (notation/analyst/insider/seasonality/corp,"
                " daily SQLite cache)"
            )
        typer.echo(
            "  Legend:  ✓(DATE) = up-to-date through DATE  +N = new rows stored"
            "  bf+N = backfilled older gap  agg = inst. flow  ERR: = failed"
        )
        typer.echo("")

        # Print table header
        header_line = (
            f"  {'[Index] Ticker':<15}  {'Candles':<13}  {'Summaries':<18}"
            f"  {'Tracked Flow':<18}  {'Inst. Flow':<18}"
        )
        sep_line = (
            f"  {'─────── ──────':<15}  {'─────────────':<13}  {'──────────────────':<18}"
            f"  {'──────────────────':<18}  {'──────────────────':<18}"
        )
        if not event.no_meta:
            header_line += f"  {'Meta':<18}"
            sep_line += f"  {'──────────────────':<18}"
        if event.enrichment_available:
            header_line += f"  {'Enrichment':<26}"
            sep_line += f"  {'──────────────────────────':<26}"
        typer.echo(header_line)
        typer.echo(sep_line)

    def on_ticker_complete(result: FetchMarketTickerResult, index: int, total: int) -> None:
        status_line = render_fetch_market_row(
            result,
            index,
            total,
            include_meta=not no_meta,
            include_enrichment=not no_enrichment and broker_provider_name == "stockbit",
        )
        status_color = fetch_market_row_color(result)
        typer.echo(typer.style(status_line, fg=status_color))

    # Execute the workflow
    try:
        req = FetchMarketCommandWorkflowRequest(
            tickers=list(tickers) if tickers else [],
            universe=universe,
            days=resolved_days,
            db_path=resolved_db,
            candles_provider=candles_provider,
            broker_provider=broker_provider_obj,
            broker_provider_name=broker_provider_name,
            refresh=refresh,
            candles_only=candles_only,
            broker_only=broker_only,
            no_meta=no_meta,
            no_enrichment=no_enrichment,
            no_calendar=no_calendar,
            no_macro_calendar=no_macro_calendar,
        )
        result = workflow_use_case.execute(
            req,
            on_ticker_complete=on_ticker_complete,
            on_start=on_start,
        )
    except UniverseNotFoundError as e:
        raise_user_error(str(e), tip="See: saham fetch universe list")
    except FileNotFoundError as e:
        raise_data_unavailable(str(e), tip="Run: saham fetch universe update")
    except ValueError as e:
        msg = str(e)
        if "session" in msg.lower() or "login" in msg.lower() or "auth" in msg.lower():
            raise_data_unavailable(msg, tip="Run: saham fetch stockbit login")
        raise_user_error(msg)

    response = result.response

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
            (
                f"Broker history shorter than --days {days} for "
                f"{len(response.broker_backfills)} ticker(s); "
                "older broker gaps were fetched automatically:"
            )
            if response.broker_backfills
            else ""
        ),
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
        expected_trading_day=result.expected_trading_day,
        enrichment_available=response.enrichment_available,
        market_is_open=result.header.is_open if result.header else False,
    )

    typer.echo(f"Calendar: {result.calendar_status}")
    typer.echo(f"Macro calendar: {result.macro_calendar_status}")

    if response.pit_coverage:
        render_enrichment_pit_coverage(response.pit_coverage)

    # Fetch MCE global context tickers (VIX, EIDO, USD/IDR)
    if result.context_statuses:
        typer.echo(f"  Context tickers: {', '.join(result.context_statuses)}")
