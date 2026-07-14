"""
CLI command for fetching broker summary data.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.fetch_broker_display import display_recent_fetch_summary
from src.adapters.cli.fetch_broker_error_display import (
    echo_unknown_provider,
    exit_broker_auth_error,
    exit_broker_provider_error,
    exit_value_error,
)
from src.adapters.cli.fetch_broker_market_status_display import (
    echo_stockbit_market_status,
)
from src.adapters.cli.fetch_broker_provider_factory import PROVIDERS
from src.adapters.cli.fetch_broker_workflow_factory import (
    create_fetch_broker_summary_workflow,
)
from src.application.use_case.fetch_broker_command_workflows import (
    FetchBrokerSummaryWorkflowRequest,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProviderError,
)
from src.infrastructure.config.app_config import load_app_config


def broker_fetch(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    days: Annotated[
        Optional[int],
        typer.Option("--days", "-d", help="Number of days to fetch"),
    ] = None,
    start: Annotated[
        Optional[str],
        typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)"),
    ] = None,
    end: Annotated[
        Optional[str],
        typer.Option("--end", "-e", help="End date (YYYY-MM-DD)"),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", "-r", help="Force refresh from provider"),
    ] = False,
    provider_name: Annotated[
        Optional[str],
        typer.Option(
            "--provider", "-P",
            help=f"Data provider ({', '.join(PROVIDERS)})",
        ),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """
    Fetch broker summary data for a stock.

    Fetches broker flow data and caches locally.
    Subsequent calls use cached data unless --refresh is specified.

    Providers:
        idx       - IDX public API (default, no auth required)
        stockbit - Stockbit browser session (run 'saham fetch stockbit login')

    Examples:
        saham fetch broker BBCA                       # IDX provider (default)
        saham fetch broker BBCA --provider stockbit
        saham fetch broker BBCA --days 90             # Last 90 days
        saham fetch broker BBCA --refresh             # Force refresh
        saham fetch broker BBCA -s 2024-01-01 -e 2024-06-30
    """
    cfg = load_app_config()
    resolved_days = days if days is not None else cfg.broker.default_days
    resolved_provider = provider_name or cfg.broker.provider
    resolved_db = db_path or Path(cfg.storage.db_path)

    # Validate provider
    if resolved_provider not in PROVIDERS:
        echo_unknown_provider(resolved_provider, PROVIDERS)
        raise typer.Exit(1)

    # Parse dates
    if start:
        start_date = date.fromisoformat(start)
    else:
        start_date = date.today() - timedelta(days=resolved_days)

    if end:
        end_date = date.fromisoformat(end)
    else:
        end_date = date.today()

    echo_stockbit_market_status()
    typer.echo(f"Fetching broker data for {ticker.upper()}...")
    typer.echo(f"Provider: {resolved_provider} | Date range: {start_date} to {end_date}")

    try:
        workflow = create_fetch_broker_summary_workflow(resolved_provider, resolved_db)
        result = workflow.execute(
            FetchBrokerSummaryWorkflowRequest(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                days=resolved_days,
                refresh=refresh,
                provider_name=resolved_provider,
            )
        )

        response = result.response
        source = "cache" if response.from_cache else resolved_provider
        typer.echo(
            typer.style(f"Loaded {len(response.summaries)} days from {source}",
                       fg=typer.colors.GREEN)
        )

        if result.exact_flow_saved_count > 0:
            typer.echo(
                typer.style(
                    f"Saved {result.exact_flow_saved_count} exact foreign-flow points",
                    fg=typer.colors.CYAN,
                )
            )

        display_recent_fetch_summary(response.summaries)

    except ValueError as e:
        exit_value_error(e)
    except BrokerDataAuthError as e:
        exit_broker_auth_error(e)
    except BrokerDataProviderError as e:
        exit_broker_provider_error(e)
