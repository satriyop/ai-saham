"""
CLI: view ticker flow — foreign flow summary table for a stock.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_ticker_flow_table_display import display_ticker_flow_table
from src.application.use_case.fetch_broker_data_use_case import GetBrokerDataUseCase
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


def ticker_flow(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to show"),
    ] = 10,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    Show foreign flow summary table for a stock (broker_summaries).

    Examples:
        saham view ticker flow BBCA --days 20
        saham view ticker flow BBCA --format json
    """
    cfg = load_app_config()
    db_path = db_path or Path(cfg.storage.db_path)
    fmt = fmt or cfg.analysis.format
    repository = SQLiteBrokerRepository(db_path)
    use_case = GetBrokerDataUseCase(repository)

    end_date = date.today()
    start_date = end_date - timedelta(days=days + 10)

    summaries = use_case.execute(ticker, start_date, end_date)

    if not summaries:
        typer.echo(
            typer.style("No data found. ", fg=typer.colors.YELLOW)
            + f"Run 'saham fetch broker {ticker}' or 'saham fetch market' first."
        )
        raise typer.Exit(1)

    summaries = summaries[-days:]

    if fmt == "json":
        import json as _json

        typer.echo(_json.dumps([s.to_dict() for s in summaries], indent=2, default=str))
        return

    display_ticker_flow_table(ticker, summaries)
