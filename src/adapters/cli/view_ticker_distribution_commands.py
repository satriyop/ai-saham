"""
CLI: view ticker distribution — cross-broker counterparty matrix for a stock.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_ticker_distribution_display import (
    display_broker_distribution,
)
from src.adapters.cli.view_ticker_distribution_provider_factory import (
    create_broker_distribution_provider,
)
from src.infrastructure.config.app_config import load_app_config


def ticker_distribution(
    ticker: Annotated[str, typer.Argument(help="Ticker symbol (e.g. BBCA)")],
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Show cross-broker counterparty distribution for a ticker.

    Reveals which brokers bought FROM whom and sold TO whom today.

    Examples:
        saham view ticker distribution BBCA
        saham view ticker distribution GOTO --db /path/to/data.db
    """
    db_path = db_path or Path(load_app_config().storage.db_path)
    provider = create_broker_distribution_provider(db_path)
    snapshot = provider.get_distribution(ticker.upper())

    if snapshot is None:
        typer.echo(
            typer.style(
                f"No broker distribution data cached for {ticker.upper()}. ",
                fg=typer.colors.YELLOW,
            )
            + "Run 'saham fetch market' with Stockbit first."
        )
        raise typer.Exit(1)

    display_broker_distribution(snapshot)
