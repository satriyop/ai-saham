"""
CLI command for fetching broker foreign-flow history.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.fetch_broker_display import display_history_fetch_preview
from src.adapters.cli.fetch_broker_error_display import (
    exit_stockbit_provider_error,
    exit_unexpected_error,
    exit_value_error,
)
from src.adapters.cli.fetch_broker_workflow_factory import (
    create_broker_flow_history_workflow,
)
from src.application.use_case.fetch_broker_command_workflows import (
    FetchBrokerFlowHistoryWorkflowRequest,
)
from src.domain.ports.broker_data_provider import BrokerDataProviderError
from src.infrastructure.config.app_config import load_app_config


def broker_history(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g. BBCA)")],
    days: Annotated[
        int,
        typer.Option("--days", help="How many trading days to fetch (1–365)", min=1, max=365),
    ] = 365,
    provider: Annotated[
        str,
        typer.Option("--provider", help="Provider: stockbit"),
    ] = "stockbit",
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Fetch and store daily foreign broker flow history for a stock (time-series).

    Unlike 'saham fetch broker' (which stores full broker breakdown), this command
    fetches the lightweight daily net-flow time-series with exact avg_price
    from Stockbit's historical endpoint. Ideal for backtesting and trend analysis.

    Results are stored in the foreign-flow time-series table with source='stockbit'.

    Examples:
        saham fetch broker-history BBCA
        saham fetch broker-history BBCA --days 30
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    ticker = ticker.upper()
    typer.echo(f"\nFetching {days}-day flow history for {ticker}...")

    try:
        workflow = create_broker_flow_history_workflow(provider, resolved_db)
        result = workflow.execute(
            FetchBrokerFlowHistoryWorkflowRequest(
                ticker=ticker,
                days=days,
            )
        )
    except ValueError as e:
        exit_value_error(e)
    except BrokerDataProviderError as e:
        exit_stockbit_provider_error(e)
    except Exception as e:
        exit_unexpected_error(e)

    if not result.points:
        typer.echo(typer.style("No historical data returned.", fg=typer.colors.YELLOW))
        return

    typer.echo(
        typer.style(
            f"Saved {result.saved_count} foreign-flow points for {ticker} → {resolved_db}",
            fg=typer.colors.GREEN,
        )
    )

    display_history_fetch_preview(ticker, result.points)
