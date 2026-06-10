"""
CLI commands for terminal ASCII charting.

Provides the 'saham chart' command group with three sub-commands:
  price   — Close price line with optional SMA/EMA overlays
  rsi     — RSI line with overbought/oversold bands
  volume  — Daily volume bar chart

Requires: plotext (pip install plotext)

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.bootstrap import create_indicator_registry
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository

chart_app = typer.Typer(
    name="chart",
    help="Terminal ASCII charts for IDX stocks",
    no_args_is_help=True,
)

DEFAULT_DB_PATH = Path("data.db")


def _require_plotext():
    """Import plotext or abort with helpful message."""
    try:
        import plotext as plt
        return plt
    except ImportError:
        typer.echo("Error: plotext not installed.", err=True)
        typer.echo("Run: pip install plotext", err=True)
        raise typer.Exit(1)


def _load_candles(ticker: str, days: int, db_path: Path):
    """Load candles from SQLite, exit with message on failure."""
    repository = SQLiteMarketRepository(db_path=db_path)
    try:
        candles = repository.get_candles(ticker.upper())
    except Exception as e:
        typer.echo(f"Error loading data: {e}", err=True)
        raise typer.Exit(1)

    if not candles:
        typer.echo(f"No cached data for {ticker.upper()}.", err=True)
        typer.echo(f"Run: saham fetch {ticker.upper()}", err=True)
        raise typer.Exit(1)

    return candles[-days:]


@chart_app.command("price")
def chart_price(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g., BBCA)")],
    sma: Annotated[
        Optional[int],
        typer.Option("--sma", help="SMA period overlay (e.g. 20)"),
    ] = 20,
    ema: Annotated[
        Optional[int],
        typer.Option("--ema", help="EMA period overlay (0 to disable)"),
    ] = None,
    days: Annotated[int, typer.Option("--days", "-d", help="Days of history", min=5)] = 90,
    width: Annotated[int, typer.Option("--width", help="Chart width (columns)", min=40)] = 100,
    height: Annotated[int, typer.Option("--height", help="Chart height (rows)", min=10)] = 24,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="SQLite database path")] = None,
) -> None:
    """
    Plot close price with SMA/EMA overlays.

    Examples:
        saham chart price BBCA
        saham chart price BBCA --sma 20 --ema 9 --days 120
        saham chart price BBCA --sma 50 --days 365
    """
    plt = _require_plotext()
    resolved_db = db_path or DEFAULT_DB_PATH
    candles = _load_candles(ticker, days, resolved_db)

    dates = [str(c.date) for c in candles]
    closes = [float(c.close) for c in candles]

    plt.clf()
    plt.date_form("Y-m-d")
    plt.plot_size(width, height)
    plt.title(f"{ticker.upper()} — Close Price (last {len(candles)} days)")
    plt.xlabel("Date")
    plt.ylabel("Price (IDR)")

    plt.plot(dates, closes, label="Close")

    registry = create_indicator_registry()

    if sma and sma > 0:
        try:
            sma_values = registry.compute("SMA", candles, sma)
            if sma_values:
                sma_dates = [str(d) for d, _ in sma_values]
                sma_prices = [float(v) for _, v in sma_values]
                plt.plot(sma_dates, sma_prices, label=f"SMA({sma})")
        except Exception:
            typer.echo(f"Warning: Could not compute SMA({sma})", err=True)

    if ema and ema > 0:
        try:
            ema_values = registry.compute("EMA", candles, ema)
            if ema_values:
                ema_dates = [str(d) for d, _ in ema_values]
                ema_prices = [float(v) for _, v in ema_values]
                plt.plot(ema_dates, ema_prices, label=f"EMA({ema})")
        except Exception:
            typer.echo(f"Warning: Could not compute EMA({ema})", err=True)

    plt.show()


@chart_app.command("rsi")
def chart_rsi(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g., BBCA)")],
    period: Annotated[int, typer.Option("--period", "-p", help="RSI period", min=2)] = 14,
    days: Annotated[int, typer.Option("--days", "-d", help="Days of history", min=5)] = 90,
    width: Annotated[int, typer.Option("--width", help="Chart width (columns)", min=40)] = 100,
    height: Annotated[int, typer.Option("--height", help="Chart height (rows)", min=10)] = 18,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="SQLite database path")] = None,
) -> None:
    """
    Plot RSI with overbought (70) and oversold (30) reference lines.

    Examples:
        saham chart rsi BBCA
        saham chart rsi BBCA --period 9 --days 120
    """
    plt = _require_plotext()
    resolved_db = db_path or DEFAULT_DB_PATH
    candles = _load_candles(ticker, days, resolved_db)

    registry = create_indicator_registry()

    try:
        rsi_values = registry.compute("RSI", candles, period)
    except Exception as e:
        typer.echo(f"Error computing RSI: {e}", err=True)
        raise typer.Exit(1)

    if not rsi_values:
        typer.echo(f"Insufficient data to compute RSI({period}) for {ticker.upper()}", err=True)
        raise typer.Exit(1)

    dates = [str(d) for d, _ in rsi_values]
    values = [float(v) for _, v in rsi_values]
    overbought = [70.0] * len(dates)
    oversold = [30.0] * len(dates)

    plt.clf()
    plt.date_form("Y-m-d")
    plt.plot_size(width, height)
    plt.title(f"{ticker.upper()} — RSI({period}) (last {len(candles)} days)")
    plt.xlabel("Date")
    plt.ylabel("RSI")
    plt.ylim(0, 100)

    plt.plot(dates, values, label=f"RSI({period})")
    plt.plot(dates, overbought, label="Overbought 70")
    plt.plot(dates, oversold, label="Oversold 30")

    plt.show()


@chart_app.command("volume")
def chart_volume(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g., BBCA)")],
    days: Annotated[int, typer.Option("--days", "-d", help="Days of history", min=5)] = 60,
    width: Annotated[int, typer.Option("--width", help="Chart width (columns)", min=40)] = 100,
    height: Annotated[int, typer.Option("--height", help="Chart height (rows)", min=10)] = 18,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="SQLite database path")] = None,
) -> None:
    """
    Plot daily volume as a bar chart.

    Examples:
        saham chart volume BBCA
        saham chart volume BBCA --days 30
    """
    plt = _require_plotext()
    resolved_db = db_path or DEFAULT_DB_PATH
    candles = _load_candles(ticker, days, resolved_db)

    dates = [str(c.date) for c in candles]
    volumes = [c.volume for c in candles]

    plt.clf()
    plt.date_form("Y-m-d")
    plt.plot_size(width, height)
    plt.title(f"{ticker.upper()} — Daily Volume (last {len(candles)} days)")
    plt.xlabel("Date")
    plt.ylabel("Volume (lots)")

    plt.bar(dates, volumes, label="Volume")

    plt.show()
