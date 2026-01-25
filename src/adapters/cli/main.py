"""
CLI adapter for stock analysis.

This is the entry point for the command-line interface.
Uses Typer for CLI framework.

Layer: Adapter
Depends on: Application use cases, Infrastructure implementations
"""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.compute_ema import (
    ComputeEMARequest,
    ComputeEMAUseCase,
)
from src.application.use_case.compute_rsi import (
    ComputeRSIRequest,
    ComputeRSIUseCase,
)
from src.application.use_case.compute_sma import (
    ComputeSMARequest,
    ComputeSMAUseCase,
)
from src.application.use_case.fetch_market_data import (
    FetchMarketDataRequest,
    FetchMarketDataUseCase,
)
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)

app = typer.Typer(
    name="saham",
    help="Local-first stock analysis CLI for Indonesia Stock Exchange (IDX)",
    no_args_is_help=True,
)

# Default configuration
DEFAULT_DB_PATH = Path.home() / ".ai-saham" / "data.db"
DEFAULT_DAYS = 365
DEFAULT_MARKET_SUFFIX = ".JK"


@app.command()
def fetch(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history to fetch"),
    ] = DEFAULT_DAYS,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", "-r", help="Force refresh from provider (ignore cache)"),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Fetch daily OHLCV data for an IDX stock ticker.

    Data is cached locally after first fetch. Subsequent calls use cached data
    unless --refresh is specified.

    Examples:
        saham fetch BBCA
        saham fetch BBRI --days 730
        saham fetch TLKM --refresh
    """
    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Wire up dependencies
    provider = YahooFinanceProvider(market_suffix=DEFAULT_MARKET_SUFFIX)
    repository = SQLiteMarketRepository(db_path=resolved_db_path)
    use_case = FetchMarketDataUseCase(provider=provider, repository=repository)

    # Execute use case
    request = FetchMarketDataRequest(ticker=ticker, days=days, refresh=refresh)

    typer.echo(f"Fetching {ticker.upper()}...")

    try:
        response = use_case.execute(request)

        if not response.candles:
            typer.echo(f"No data found for {ticker.upper()}", err=True)
            raise typer.Exit(1)

        # Display results
        typer.echo(f"\nTicker: {response.ticker}")
        typer.echo(f"Source: {response.source}")
        typer.echo(f"Records: {response.count}")

        if response.date_range:
            start, end = response.date_range
            typer.echo(f"Date range: {start} to {end}")

        typer.echo(f"\nDatabase: {resolved_db_path}")

        # Show latest candle
        if response.candles:
            latest = response.candles[-1]
            typer.echo(f"\nLatest ({latest.date}):")
            typer.echo(f"  Open:   {latest.open:>12}")
            typer.echo(f"  High:   {latest.high:>12}")
            typer.echo(f"  Low:    {latest.low:>12}")
            typer.echo(f"  Close:  {latest.close:>12}")
            typer.echo(f"  Volume: {latest.volume:>12,}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Failed to fetch data: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def sma(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="SMA period (number of days)"),
    ] = 20,
    field: Annotated[
        str,
        typer.Option("--field", "-f", help="Price field (open/high/low/close)"),
    ] = "close",
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history to analyze"),
    ] = DEFAULT_DAYS,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Calculate Simple Moving Average (SMA) for an IDX stock.

    Requires cached data (run 'saham fetch TICKER' first).

    Examples:
        saham sma BBCA
        saham sma BBRI --period 50
        saham sma TLKM --period 200 --field open
        saham sma ASII --days 730
    """
    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Wire up dependencies
    repository = SQLiteMarketRepository(db_path=resolved_db_path)
    use_case = ComputeSMAUseCase(repository=repository)

    # Execute use case
    request = ComputeSMARequest(
        ticker=ticker,
        period=period,
        price_field=field,
        days=days,
    )

    typer.echo(f"Computing SMA({period}) for {ticker.upper()}...")

    try:
        response = use_case.execute(request)

        if not response.has_values:
            typer.echo(f"\nInsufficient data for {ticker.upper()}", err=True)
            typer.echo(f"Candles available: {response.candle_count}", err=True)
            typer.echo(f"Required for SMA({period}): {period}", err=True)
            typer.echo(f"\nRun: saham fetch {ticker.upper()}", err=True)
            raise typer.Exit(1)

        # Display summary
        typer.echo(f"\nTicker: {response.ticker}")
        typer.echo(f"Period: SMA({response.period})")
        typer.echo(f"Price Field: {response.price_field}")
        typer.echo(f"Candles: {response.candle_count}")
        typer.echo(f"SMA Values: {response.sma_count}")

        if response.date_range:
            start, end = response.date_range
            typer.echo(f"Date Range: {start} to {end}")

        # Display full series
        typer.echo(f"\n{'Date':<12} {'SMA':>14}")
        typer.echo("-" * 27)
        for date_val, sma_val in response.values:
            typer.echo(f"{date_val!s:<12} {sma_val:>14.2f}")

        # Summary statistics
        if response.values:
            sma_only = [val for _, val in response.values]
            typer.echo(f"\nSummary:")
            typer.echo(f"  Latest:  {sma_only[-1]:>14.2f}")
            typer.echo(f"  Highest: {max(sma_only):>14.2f}")
            typer.echo(f"  Lowest:  {min(sma_only):>14.2f}")
            avg_sma = sum(sma_only, Decimal("0")) / len(sma_only)
            typer.echo(f"  Average: {avg_sma:>14.2f}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Failed to compute SMA: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def ema(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="EMA period (number of days)"),
    ] = 20,
    field: Annotated[
        str,
        typer.Option("--field", "-f", help="Price field (open/high/low/close)"),
    ] = "close",
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history to display"),
    ] = DEFAULT_DAYS,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Calculate Exponential Moving Average (EMA) for an IDX stock.

    Uses SMA-seeded initialization (professional-grade, matches TradingView).
    Includes warm-up buffer handling to ensure converged values.

    Requires cached data (run 'saham fetch TICKER' first).

    Examples:
        saham ema BBCA
        saham ema BBRI --period 50
        saham ema TLKM --period 200 --field high
        saham ema ASII --days 730
    """
    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Wire up dependencies
    repository = SQLiteMarketRepository(db_path=resolved_db_path)
    use_case = ComputeEMAUseCase(repository=repository)

    # Execute use case
    request = ComputeEMARequest(
        ticker=ticker,
        period=period,
        price_field=field,
        days=days,
    )

    typer.echo(f"Computing EMA({period}) for {ticker.upper()}...")

    try:
        response = use_case.execute(request)

        if not response.has_values:
            typer.echo(f"\nInsufficient data for {ticker.upper()}", err=True)
            typer.echo(f"Candles available: {response.candle_count}", err=True)
            typer.echo(f"Required for EMA({period}): {period}", err=True)
            typer.echo(f"\nRun: saham fetch {ticker.upper()}", err=True)
            raise typer.Exit(1)

        # Display summary
        typer.echo(f"\nTicker: {response.ticker}")
        typer.echo(f"Period: EMA({response.period})")
        typer.echo(f"Price Field: {response.price_field}")
        typer.echo(f"Candles (incl. warm-up): {response.candle_count}")
        typer.echo(f"EMA Values: {response.ema_count}")

        if response.date_range:
            start, end = response.date_range
            typer.echo(f"Date Range: {start} to {end}")

        # Display full series
        typer.echo(f"\n{'Date':<12} {'EMA':>14}")
        typer.echo("-" * 27)
        for date_val, ema_val in response.values:
            typer.echo(f"{date_val!s:<12} {ema_val:>14.2f}")

        # Summary statistics
        if response.values:
            ema_only = [val for _, val in response.values]
            typer.echo(f"\nSummary:")
            typer.echo(f"  Latest:  {ema_only[-1]:>14.2f}")
            typer.echo(f"  Highest: {max(ema_only):>14.2f}")
            typer.echo(f"  Lowest:  {min(ema_only):>14.2f}")
            avg_ema = sum(ema_only, Decimal("0")) / len(ema_only)
            typer.echo(f"  Average: {avg_ema:>14.2f}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Failed to compute EMA: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def rsi(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="RSI period (number of days)"),
    ] = 14,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history to display"),
    ] = DEFAULT_DAYS,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Calculate Relative Strength Index (RSI) for an IDX stock.

    Uses Wilder's smoothed moving average (professional-grade, matches TradingView).
    Includes warm-up buffer handling to ensure converged values.

    RSI values range from 0-100:
    - Above 70: Potentially overbought
    - Below 30: Potentially oversold

    Requires cached data (run 'saham fetch TICKER' first).

    Examples:
        saham rsi BBCA
        saham rsi BBRI --period 7
        saham rsi TLKM --period 21 --days 180
    """
    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Wire up dependencies
    repository = SQLiteMarketRepository(db_path=resolved_db_path)
    use_case = ComputeRSIUseCase(repository=repository)

    # Execute use case
    request = ComputeRSIRequest(
        ticker=ticker,
        period=period,
        days=days,
    )

    typer.echo(f"Computing RSI({period}) for {ticker.upper()}...")

    try:
        response = use_case.execute(request)

        if not response.has_values:
            typer.echo(f"\nInsufficient data for {ticker.upper()}", err=True)
            typer.echo(f"Candles available: {response.candle_count}", err=True)
            typer.echo(f"Required for RSI({period}): {period + 1}", err=True)
            typer.echo(f"\nRun: saham fetch {ticker.upper()}", err=True)
            raise typer.Exit(1)

        # Display summary
        typer.echo(f"\nTicker: {response.ticker}")
        typer.echo(f"Period: RSI({response.period})")
        typer.echo(f"Candles (incl. warm-up): {response.candle_count}")
        typer.echo(f"RSI Values: {response.rsi_count}")

        if response.date_range:
            start, end = response.date_range
            typer.echo(f"Date Range: {start} to {end}")

        # Display full series
        typer.echo(f"\n{'Date':<12} {'RSI':>10}")
        typer.echo("-" * 23)
        for date_val, rsi_val in response.values:
            typer.echo(f"{date_val!s:<12} {rsi_val:>10.2f}")

        # Summary statistics
        if response.values:
            rsi_only = [val for _, val in response.values]
            typer.echo(f"\nSummary:")
            typer.echo(f"  Latest:  {rsi_only[-1]:>10.2f}")
            typer.echo(f"  Highest: {max(rsi_only):>10.2f}")
            typer.echo(f"  Lowest:  {min(rsi_only):>10.2f}")
            avg_rsi = sum(rsi_only, Decimal("0")) / len(rsi_only)
            typer.echo(f"  Average: {avg_rsi:>10.2f}")

            # Overbought/oversold analysis
            latest_rsi = rsi_only[-1]
            if latest_rsi > Decimal("70"):
                typer.echo(f"\n  Status: OVERBOUGHT (RSI > 70)")
            elif latest_rsi < Decimal("30"):
                typer.echo(f"\n  Status: OVERSOLD (RSI < 30)")
            else:
                typer.echo(f"\n  Status: NEUTRAL (30 <= RSI <= 70)")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Failed to compute RSI: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo("saham v0.1.0")
    typer.echo("Local-first stock analysis CLI")


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
