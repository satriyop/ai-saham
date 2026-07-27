"""
CLI command for scanning foreign broker top accumulation.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.fetch_broker_display import display_foreign_top_scan
from src.adapters.cli.fetch_broker_error_display import (
    exit_stockbit_provider_error,
    exit_unexpected_error,
    exit_value_error,
)
from src.adapters.cli.fetch_broker_market_status_display import (
    echo_stockbit_market_status,
)
from src.adapters.cli.fetch_broker_workflow_factory import (
    create_foreign_top_stocks_workflow,
)
from src.application.use_case.fetch_broker_command_workflows import (
    FetchForeignTopStocksWorkflowRequest,
)
from src.domain.ports.broker_data_provider import BrokerDataProviderError
from src.infrastructure.config.app_config import load_app_config


def broker_top_foreign(
    days: Annotated[
        int,
        typer.Option("--days", help="Look-back window in days (1/3/7/30/90/365)", min=1, max=365),
    ] = 7,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max stocks to return", min=1, max=50),
    ] = 20,
    provider: Annotated[
        str,
        typer.Option("--provider", help="Provider: stockbit"),
    ] = "stockbit",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    no_save: Annotated[
        bool,
        typer.Option("--no-save", help="Do not persist results to database"),
    ] = False,
) -> None:
    """
    Ingest foreign-broker top-stock ranking into the local cache.

    Writes a snapshot for later browsing. This is a data job, not the primary
    analysis surface.

    Browse cached ranking: `saham view broker top-foreign`.
    Requires Stockbit session: `saham fetch stockbit login`.

    Examples:
        saham fetch broker-top-foreign
        saham fetch broker-top-foreign --days 7 --limit 20
        saham view broker top-foreign
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    end = date.today()
    start = end - timedelta(days=days)

    echo_stockbit_market_status(leading_blank=True)
    typer.echo(f"Foreign broker accumulation scan ({start} → {end})")
    typer.echo("─" * 55)

    try:
        workflow = create_foreign_top_stocks_workflow(provider, resolved_db)
        result = workflow.execute(
            FetchForeignTopStocksWorkflowRequest(
                days=days,
                limit=limit,
                save=not no_save,
                today=end,
            )
        )
    except ValueError as e:
        exit_value_error(e)
    except BrokerDataProviderError as e:
        exit_stockbit_provider_error(e)
    except Exception as e:
        exit_unexpected_error(e)

    if not result.snapshots:
        typer.echo(typer.style("No data returned.", fg=typer.colors.YELLOW))
        typer.echo("Run: saham fetch stockbit spy --target broker-scan")
        return

    # Auto-save notice
    if not no_save:
        if result.save_warning:
            typer.echo(
                typer.style(
                    f"  Warning: could not save to DB: {result.save_warning}",
                    fg=typer.colors.YELLOW,
                ),
                err=True,
            )
        elif result.saved_count > 0:
            typer.echo(
                typer.style(
                    f"  Saved {result.saved_count} snapshots → {resolved_db}",
                    fg=typer.colors.CYAN,
                )
            )

    display_foreign_top_scan(result.snapshots)

    typer.echo("")
    typer.echo(f"Showing {len(result.snapshots)} stocks. Use --limit to adjust.")
