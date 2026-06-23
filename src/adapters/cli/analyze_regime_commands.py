"""
CLI implementation functions for saham analyze regime command.

Public command registration lives in lifecycle routers:
  saham analyze regime

Layer: Adapter
"""

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.analyze_regime_display import display_regime
from src.application.services.universe_loader import (
    UniverseNotFoundError,
    resolve_tickers,
)
from src.application.use_case.market_regime_use_case import (
    MarketRegimeRequest,
    MarketRegimeUseCase,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.swing_config import load_swing_config
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
_SC = load_swing_config()


def regime(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols for breadth context"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option("--universe", "-u", help="Universe name or 'cached' — see `saham fetch universe list`"),
    ] = APP_CFG.analysis.regime_universe,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker, e.g. ^JKSE"),
    ] = APP_CFG.analysis.benchmark,
    as_of: Annotated[
        Optional[str],
        typer.Option("--as-of", help="Regime date, YYYY-MM-DD (default: today)"),
    ] = None,
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
    Show deterministic IHSG market regime context for swing trading.

    Uses local cached benchmark candles, universe breadth, and broker flow data.
    """
    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        regime_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as e:
        typer.echo(f"Error: invalid date format: {e}", err=True)
        raise typer.Exit(1)

    try:
        ticker_list = resolve_tickers(
            universe=universe,
            explicit=list(tickers) if tickers else [],
            db_path=resolved_db,
        )
    except (UniverseNotFoundError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not ticker_list:
        typer.echo(
            "No tickers for regime breadth. Specify --universe or ticker arguments.",
            err=True,
        )
        raise typer.Exit(1)

    use_case = MarketRegimeUseCase(
        market_repository=SQLiteMarketRepository(db_path=resolved_db),
        broker_repository=SQLiteBrokerRepository(resolved_db),
    )
    try:
        response = use_case.execute(MarketRegimeRequest(
            universe=ticker_list,
            benchmark_ticker=benchmark,
            as_of_date=regime_date,
            breadth_sma_period=_SC.regime_breadth_sma_period,
            benchmark_sma_fast=_SC.regime_benchmark_sma_fast,
            benchmark_sma_slow=_SC.regime_benchmark_sma_slow,
            breadth_threshold_pct=_SC.regime_breadth_threshold_pct,
        ))
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, default=str))
        return

    display_regime(response)
