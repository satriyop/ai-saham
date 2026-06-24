"""
CLI commands for saham view market-context.

Reads cached market data from SQLite (no network calls).
Data must be pre-fetched via `saham fetch market`.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_market_context_display import (
    display_market_context,
    display_market_context_json,
)
from src.application.services.market_context_engine import MarketContextEngine
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.market_context_config import load_market_context_config
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_context_repository import SQLiteMarketContextRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)


def market_context_show(
    as_of: Annotated[
        Optional[str],
        typer.Option("--date", help="Context date, YYYY-MM-DD (default: today)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe for idx_breadth factor (default: regime_universe config)"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show score bar and full rationale per factor"),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Show current market regime context (cross-market + IDX-internal factors).

    Reads cached candles — run `saham fetch market` first to ensure fresh data.
    """
    resolved_db = db_path or DEFAULT_DB_PATH

    try:
        context_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

    resolved_universe = universe or APP_CFG.analysis.regime_universe
    try:
        ticker_list = resolve_tickers(
            universe=resolved_universe,
            explicit=[],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError):
        ticker_list = []

    cfg = load_market_context_config()
    engine = MarketContextEngine(
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
        config=cfg,
        universe=ticker_list,
        broker_repository=SQLiteBrokerRepository(db_path=resolved_db),
        context_repository=SQLiteMarketContextRepository(db_path=resolved_db),
    )

    try:
        context = engine.evaluate(as_of_date=context_date)
    except Exception as e:
        typer.echo(f"Error evaluating market context: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        display_market_context_json(context)
        return

    display_market_context(context, verbose=verbose)
