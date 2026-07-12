"""
CLI command for computing a single technical indicator.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.indicator_display import (
    print_compute_header,
    print_compute_summary,
    print_compute_table,
    print_db_not_found_error,
    print_no_data_error,
)
from src.application.services.bootstrap import create_indicator_registry
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_DAYS = APP_CFG.market.default_days


def compute(
    indicator: Annotated[
        str,
        typer.Argument(
            help="Indicator name (SMA, RSI, ATR, or custom formula)"
        ),
    ],
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="Period (ignored for formula indicators)", min=1),
    ] = 14,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Days of history to load", min=1),
    ] = DEFAULT_DAYS,
    tail: Annotated[
        int,
        typer.Option("--tail", "-t", help="Show last N values (default 30)", min=1),
    ] = 30,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
    ] = None,
) -> None:
    """
    Compute any indicator values for a stock.

    Works with built-in indicators (SMA, EMA, RSI), plugins (ATR, VR, MFI…),
    and custom formulas created via `saham indicator create`.

    Examples:
        saham indicator compute RSI BBCA
        saham indicator compute SMA BBCA --period 50
        saham indicator compute SMOOTH_RSI BBCA --tail 10
        saham indicator compute ATR BBCA --days 180
    """
    registry = create_indicator_registry()
    indicator_upper = indicator.upper()
    ticker_upper = ticker.upper()

    if not registry.is_registered(indicator_upper):
        typer.echo(f"[error] Unknown indicator: {indicator_upper}", err=True)
        typer.echo("\nAvailable indicators:", err=True)
        for name in sorted(registry.list_indicators()):
            typer.echo(f"  {name}", err=True)
        raise typer.Exit(1)

    resolved_db = db_path or DEFAULT_DB_PATH
    typer.echo(f"Loading {ticker_upper} · {indicator_upper} from {resolved_db}...")

    try:
        repository = SQLiteMarketRepository(db_path=resolved_db)
        candles = repository.get_candles(ticker_upper)

        if not candles:
            print_no_data_error(ticker_upper, days)
            raise typer.Exit(1)

        if len(candles) < days - 7:
            typer.echo(
                f"[warning] Only {len(candles)} trading days cached, {days} requested.",
                err=True,
            )
            typer.echo(
                f"           Run: saham fetch market {ticker_upper} --days {days}",
                err=True,
            )

        if len(candles) > days:
            candles = candles[-days:]

        values = registry.compute(indicator_upper, candles, period)

        if not values:
            typer.echo(
                f"[error] Insufficient data for {indicator_upper}({period})."
                f" Have {len(candles)} candles.",
                err=True,
            )
            typer.echo(
                f"        Fix:   saham fetch market {ticker_upper} --days {days}", err=True
            )
            raise typer.Exit(1)

        display_values = values[-tail:] if len(values) > tail else values
        default_period = registry.get_default_period(indicator_upper)
        label = f"{indicator_upper}({period})" if default_period > 0 else indicator_upper

        print_compute_header(ticker_upper, label, values, display_count=len(display_values))
        is_rsi = indicator_upper == "RSI"
        print_compute_table(display_values, label, is_rsi)
        print_compute_summary(values, is_rsi)

    except typer.Exit:
        raise
    except FileNotFoundError:
        print_db_not_found_error(resolved_db, ticker_upper, days)
        raise typer.Exit(1)
    except Exception as e:
        msg = str(e).lower()
        if "no such table" in msg or "no data" in msg:
            print_no_data_error(ticker_upper, days)
        else:
            typer.echo(f"[error] Failed to compute {indicator_upper}: {e}", err=True)
        raise typer.Exit(1)
