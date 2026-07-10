"""
CLI command for point-in-time Stockbit enrichment snapshots.

Provides `saham fetch enrichment-history` — stores a timestamped enrichment
snapshot for a universe so signal backfill replay has point-in-time data.

Layer: Adapter
"""

import functools
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.fetch_market_display import render_enrichment_pit_coverage
from src.adapters.cli.fetch_market_enrichment_refresh import (
    fetch_enrichment,
    read_enrichment_pit_coverage,
)
from src.adapters.cli.fetch_market_provider_factory import create_broker_provider
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.infrastructure.config.app_config import APP_CFG


def fetch_enrichment_history(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name — see `saham fetch universe list`"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force/--no-force", help="Force refresh even if cached today"),
    ] = True,
) -> None:
    """Store a timestamped enrichment snapshot for all universe tickers.

    Fetches current fundamental, shareholding, analyst, notation, and forward-estimates
    data from Stockbit and stores each fetch with today's date. Re-running this
    command on a different day adds a new PIT snapshot without overwriting prior rows.

    IMPORTANT: Stockbit does not provide historical values. Only TODAY's data
    can be retrieved. Historical observations before the first snapshot will
    return UNKNOWN for market_cap_bucket, analyst consensus, shareholding, etc.
    Run this command regularly (daily or weekly) to build a useful PIT history.

    Examples:
        saham fetch enrichment-history --universe lq45
        saham fetch enrichment-history BBCA BBRI BMRI
    """
    from src.application.use_case.fetch_enrichment_history_use_case import (
        FetchEnrichmentHistoryRequest,
        FetchEnrichmentHistoryUseCase,
    )

    resolved_db = db_path or Path(APP_CFG.storage.db_path)
    today = date.today()

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

    broker_provider, broker_provider_name = create_broker_provider(None)
    if broker_provider_name != "stockbit":
        typer.echo(
            "Error: Stockbit session required for enrichment fetch. "
            "Log in with `saham fetch stockbit login` first.",
            err=True,
        )
        raise typer.Exit(1)

    universe_label = universe or f"{len(ticker_list)} tickers"
    typer.echo(f"\nFetching enrichment snapshot  universe={universe_label}  date={today}")
    typer.echo("  (Stockbit provides current values only; prior snapshots are preserved)")
    typer.echo("")

    # Wire callables — provider construction stays in the adapter
    enrich_one = functools.partial(
        fetch_enrichment, db_path=resolved_db, broker_provider=broker_provider, force_refresh=force
    )
    read_coverage = functools.partial(read_enrichment_pit_coverage, resolved_db)

    use_case = FetchEnrichmentHistoryUseCase(
        enrich_ticker=enrich_one,
        read_pit_coverage=read_coverage,
    )
    response = use_case.execute(
        FetchEnrichmentHistoryRequest(tickers=ticker_list, force_refresh=force)
    )

    for ticker, status in response.results:
        color = typer.colors.RED if status.startswith("ERR:") else typer.colors.GREEN
        typer.echo(typer.style(f"  {ticker:<8} {status}", fg=color))

    typer.echo("")
    typer.echo(
        f"Done: {response.ok_count} ok"
        + (f", {response.fail_count} failed" if response.fail_count else "")
    )
    render_enrichment_pit_coverage(response.coverage)
