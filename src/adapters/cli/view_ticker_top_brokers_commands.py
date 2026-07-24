"""
CLI: view ticker top-brokers — top desks in a stock.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_ticker_top_brokers_display import display_ticker_top_brokers
from src.application.use_case.view_ticker_top_brokers_use_case import (
    ViewTickerTopBrokersRequest,
    ViewTickerTopBrokersUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


def ticker_top_brokers(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    target_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Date (YYYY-MM-DD), default: latest"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Database path"),
    ] = None,
) -> None:
    """
    Show top broker desks for a stock on a specific date.

    Prefers market top lists from broker_summaries. When those are empty
    (typical for IDX summaries), ranks tracked brokers from broker_daily_flow
    for the same date and labels the scope clearly.

    Examples:
        saham view ticker top-brokers BBCA
        saham view ticker top-brokers BBCA --date 2024-01-15
    """
    db_path = db_path or Path(load_app_config().storage.db_path)
    repository = SQLiteBrokerRepository(db_path)
    ia_cfg = load_institutional_accumulation_config()
    use_case = ViewTickerTopBrokersUseCase(
        repository,
        foreign_broker_codes=ia_cfg.foreign_broker_codes,
    )

    query_date = date.fromisoformat(target_date) if target_date else None
    result = use_case.execute(
        ViewTickerTopBrokersRequest(ticker=ticker, target_date=query_date)
    )

    if result is None:
        if target_date:
            typer.echo(typer.style("No data for that date.", fg=typer.colors.YELLOW))
        else:
            typer.echo(
                typer.style("No data found. ", fg=typer.colors.YELLOW)
                + f"Run 'saham fetch broker {ticker}' or 'saham fetch market' first."
            )
        raise typer.Exit(1)

    display_ticker_top_brokers(
        result.ticker,
        result.summary,
        top_buyers=result.top_buyers,
        top_sellers=result.top_sellers,
        tops_scope_note=result.tops_scope_note,
    )
