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

from src.application.use_case.aggregate_indicators import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.application.use_case.assess_risk import (
    AssessRiskRequest,
    AssessRiskUseCase,
)
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
def indicators(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    sma_period: Annotated[
        int,
        typer.Option("--sma", help="SMA period (default: 20)"),
    ] = 20,
    ema_period: Annotated[
        int,
        typer.Option("--ema", help="EMA period (default: 20)"),
    ] = 20,
    rsi_period: Annotated[
        int,
        typer.Option("--rsi", help="RSI period (default: 14)"),
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
    Calculate SMA, EMA, and RSI together for an IDX stock.

    Provides a unified view of multiple indicators aligned by date.
    Only dates with all indicators present are shown.

    Requires cached data (run 'saham fetch TICKER' first).

    Examples:
        saham indicators BBCA
        saham indicators BBRI --sma 50 --ema 50
        saham indicators TLKM --rsi 7 --days 180
    """
    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Wire up dependencies
    repository = SQLiteMarketRepository(db_path=resolved_db_path)
    use_case = AggregateIndicatorsUseCase(repository=repository)

    # Execute use case
    request = AggregateIndicatorsRequest(
        ticker=ticker,
        sma_period=sma_period,
        ema_period=ema_period,
        rsi_period=rsi_period,
        days=days,
    )

    typer.echo(f"Computing indicators for {ticker.upper()}...")

    try:
        response = use_case.execute(request)

        if not response.has_values:
            typer.echo(f"\nInsufficient data for {ticker.upper()}", err=True)
            typer.echo(f"Candles available: {response.candle_count}", err=True)
            typer.echo(
                f"Required: SMA({sma_period}), EMA({ema_period}), RSI({rsi_period})",
                err=True,
            )
            typer.echo(f"\nRun: saham fetch {ticker.upper()}", err=True)
            raise typer.Exit(1)

        # Display header
        typer.echo(f"\nTicker: {response.ticker}")
        typer.echo(
            f"Periods: SMA({response.sma_period}), "
            f"EMA({response.ema_period}), RSI({response.rsi_period})"
        )
        typer.echo(f"Candles: {response.candle_count}")
        typer.echo(f"Snapshots: {response.snapshot_count}")

        if response.date_range:
            start, end = response.date_range
            typer.echo(f"Date Range: {start} to {end}")

        # Display table
        typer.echo(f"\n{'Date':<12} {'SMA':>14} {'EMA':>14} {'RSI':>10}")
        typer.echo("-" * 52)

        for snapshot in response.snapshots:
            typer.echo(
                f"{snapshot.date!s:<12} "
                f"{snapshot.sma:>14,.2f} "
                f"{snapshot.ema:>14,.2f} "
                f"{snapshot.rsi:>10.2f}"
            )

        # Summary statistics
        if response.snapshots:
            sma_values = [s.sma for s in response.snapshots]
            ema_values = [s.ema for s in response.snapshots]
            rsi_values = [s.rsi for s in response.snapshots]

            typer.echo(f"\nSummary:")
            typer.echo(
                f"  SMA  - Latest: {sma_values[-1]:>12,.2f}  "
                f"Range: [{min(sma_values):,.2f} - {max(sma_values):,.2f}]"
            )
            typer.echo(
                f"  EMA  - Latest: {ema_values[-1]:>12,.2f}  "
                f"Range: [{min(ema_values):,.2f} - {max(ema_values):,.2f}]"
            )
            typer.echo(
                f"  RSI  - Latest: {rsi_values[-1]:>12.2f}  "
                f"Range: [{min(rsi_values):.2f} - {max(rsi_values):.2f}]"
            )

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Failed to compute indicators: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def risk(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    profile: Annotated[
        str,
        typer.Option("--profile", "-p", help="Risk profile (conservative/balanced/aggressive)"),
    ] = "balanced",
    all_profiles: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show assessment for all profiles"),
    ] = False,
    sma_period: Annotated[
        int,
        typer.Option("--sma", help="SMA period (default: 20)"),
    ] = 20,
    ema_period: Annotated[
        int,
        typer.Option("--ema", help="EMA period (default: 20)"),
    ] = 20,
    rsi_period: Annotated[
        int,
        typer.Option("--rsi", help="RSI period (default: 14)"),
    ] = 14,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database"),
    ] = None,
) -> None:
    """
    Assess risk for an IDX stock based on technical indicators.

    Uses deterministic, rule-based evaluation with three risk profiles:
    - conservative: Strict thresholds, requires both indicators to agree
    - balanced: Standard thresholds, majority rules
    - aggressive: Wide thresholds, either indicator can signal

    Risk levels returned:
    - HIGH_RISK: Indicators suggest elevated risk conditions
    - MODERATE: Indicators suggest balanced/neutral conditions
    - LOW_RISK: Indicators suggest favorable risk conditions

    Requires cached data (run 'saham fetch TICKER' first).

    Examples:
        saham risk BBCA
        saham risk BBRI --profile conservative
        saham risk TLKM --all
    """
    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Wire up dependencies
    repository = SQLiteMarketRepository(db_path=resolved_db_path)
    use_case = AssessRiskUseCase(repository=repository)

    typer.echo(f"Assessing risk for {ticker.upper()}...")

    try:
        request = AssessRiskRequest(
            ticker=ticker,
            profile=profile,
            sma_period=sma_period,
            ema_period=ema_period,
            rsi_period=rsi_period,
        )

        if all_profiles:
            # Show all profiles in table format
            response = use_case.execute_all_profiles(request)

            typer.echo(f"\nTicker: {response.ticker}")
            typer.echo(f"Data Date: {response.assessments[0].snapshot_date}")
            typer.echo(
                f"\nIndicators: SMA({response.sma_period}), "
                f"EMA({response.ema_period}), RSI({response.rsi_period})"
            )

            # Show indicator values
            snapshot = response.assessments[0].indicators
            typer.echo(f"\n  SMA:  {snapshot.sma:>12,.2f}")
            typer.echo(f"  EMA:  {snapshot.ema:>12,.2f}")
            typer.echo(f"  RSI:  {snapshot.rsi:>12.2f}")

            # Table header
            typer.echo(f"\n{'Profile':<14} {'Risk Level':<12} {'Confidence':<12}")
            typer.echo("-" * 38)

            for assessment in response.assessments:
                typer.echo(
                    f"{assessment.profile_name:<14} "
                    f"{assessment.risk_level_name:<12} "
                    f"{assessment.confidence}/100"
                )

        else:
            # Show single profile with full details
            response = use_case.execute(request)
            assessment = response.assessment
            snapshot = assessment.indicators

            typer.echo(f"\nTicker: {response.ticker}")
            typer.echo(f"Profile: {response.profile}")
            typer.echo(f"Data Date: {assessment.snapshot_date}")

            typer.echo(f"\nIndicators:")
            typer.echo(f"  SMA({response.sma_period}):  {snapshot.sma:>12,.2f}")
            typer.echo(f"  EMA({response.ema_period}):  {snapshot.ema:>12,.2f}")
            typer.echo(f"  RSI({response.rsi_period}):  {snapshot.rsi:>12.2f}")

            typer.echo(f"\n{'─' * 39}")
            typer.echo("RISK ASSESSMENT")
            typer.echo(f"{'─' * 39}")

            typer.echo(f"\nRisk Level:  {assessment.risk_level_name}")
            typer.echo(f"Confidence:  {assessment.confidence}/100")

            typer.echo(f"\nRationale:")
            for reason in assessment.rationale_list:
                typer.echo(f"  • {reason}")

            typer.echo(f"\n{'─' * 39}")

        typer.echo("\nDISCLAIMER: Analysis only, not trading advice.")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Failed to assess risk: {e}", err=True)
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
