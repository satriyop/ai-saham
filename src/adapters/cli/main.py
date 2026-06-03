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

from src import __version__
from src.application.services.bootstrap import create_indicator_registry
from src.application.use_case.aggregate_indicators import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.application.use_case.create_indicator_from_intent import (
    CreateIndicatorFromIntentRequest,
    CreateIndicatorFromIntentUseCase,
)
from src.application.use_case.assess_risk import (
    AssessRiskRequest,
    AssessRiskUseCase,
)
from src.application.use_case.backtest import (
    BacktestRequest,
    BacktestUseCase,
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
from src.application.use_case.explain_risk import (
    ExplainRiskRequest,
    ExplainRiskUseCase,
)
from src.application.use_case.fetch_market_data import (
    FetchMarketDataRequest,
    FetchMarketDataUseCase,
)
from src.application.use_case.fetch_sentiment import (
    FetchSentimentRequest,
    FetchSentimentUseCase,
)
from src.application.rules.exceptions import (
    RulesError,
    RulesFileError,
    RulesSchemaError,
    RulesValidationError,
    StrategyNotFoundError,
)
from src.application.services.strategy_loader import StrategyLoader
from src.domain.ports.ai_explainer import ExplainerAuthError
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.sentiment import Sentiment, SentimentSnapshot
from src.infrastructure.ai import ExplainerFactory
from src.infrastructure.data_providers.yahoo import YahooFinanceProvider
from src.infrastructure.ai.formula_translator import FormulaTranslatorAdapter
from src.infrastructure.persistence.formula_storage import (
    FormulaStorage,
    FormulaStorageError,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)
from src.infrastructure.sentiment import SentimentFactory

app = typer.Typer(
    name="saham",
    help="Local-first stock analysis CLI for Indonesia Stock Exchange (IDX)",
    no_args_is_help=True,
)

# Register strategy subcommands
from src.adapters.cli.strategy_commands import strategy_app
app.add_typer(strategy_app, name="strategy")

# Register broker subcommands
from src.adapters.cli.broker_commands import broker_app
app.add_typer(broker_app, name="broker")

# Register skill subcommands
from src.adapters.cli.skill_commands import skill_app
app.add_typer(skill_app, name="skill")

# Register screen subcommands
from src.adapters.cli.screen_commands import screen_app
app.add_typer(screen_app, name="screen")

# Default configuration
DEFAULT_DB_PATH = Path("data.db")
DEFAULT_FORMULAS_PATH = Path("config/formulas.yaml")
DEFAULT_DAYS = 365
DEFAULT_MARKET_SUFFIX = ".JK"

# Valid options for validation
VALID_PROFILES = ["conservative", "balanced", "aggressive"]
VALID_FIELDS = ["open", "high", "low", "close"]


def validate_profile(value: str) -> str:
    """Validate risk profile option."""
    if value.lower() not in VALID_PROFILES:
        raise typer.BadParameter(
            f"Invalid profile '{value}'. Must be one of: {', '.join(VALID_PROFILES)}"
        )
    return value.lower()


def validate_field(value: str) -> str:
    """Validate price field option."""
    if value.lower() not in VALID_FIELDS:
        raise typer.BadParameter(
            f"Invalid field '{value}'. Must be one of: {', '.join(VALID_FIELDS)}"
        )
    return value.lower()


def _display_sentiment_full(
    snapshot: SentimentSnapshot,
    provider: str,
    classifier: str,
    warning: str | None = None,
) -> None:
    """Display full sentiment snapshot output.

    Args:
        snapshot: The sentiment snapshot to display
        provider: Name of news provider used
        classifier: Name of classifier used
        warning: Optional warning message
    """
    if warning:
        typer.echo(f"\nWarning: {warning}")
        return

    # Sentiment symbol map
    sentiment_symbols = {
        Sentiment.POSITIVE: "+",
        Sentiment.NEUTRAL: "=",
        Sentiment.NEGATIVE: "-",
    }

    # Overall sentiment display
    typer.echo(f"\n{'-' * 39}")
    typer.echo("SENTIMENT SNAPSHOT")
    typer.echo(f"{'-' * 39}")

    # Get the count for the winning sentiment
    sentiment_counts = {
        Sentiment.POSITIVE: snapshot.positive_count,
        Sentiment.NEUTRAL: snapshot.neutral_count,
        Sentiment.NEGATIVE: snapshot.negative_count,
    }
    winning_count = sentiment_counts[snapshot.overall_sentiment]

    typer.echo(f"\nOverall: {snapshot.overall_sentiment.value.upper()}")
    typer.echo(
        f"Confidence: {winning_count}/{snapshot.total_count} headlines ({snapshot.confidence_pct}%)"
    )

    typer.echo("\nBreakdown:")
    total = snapshot.total_count or 1  # Avoid division by zero
    pos_pct = int(snapshot.positive_count / total * 100)
    neu_pct = int(snapshot.neutral_count / total * 100)
    neg_pct = int(snapshot.negative_count / total * 100)
    typer.echo(f"  Positive:  {snapshot.positive_count} ({pos_pct}%)")
    typer.echo(f"  Neutral:   {snapshot.neutral_count} ({neu_pct}%)")
    typer.echo(f"  Negative:  {snapshot.negative_count} ({neg_pct}%)")

    # Show recent headlines (max 5)
    if snapshot.headlines:
        typer.echo("\nRecent Headlines:")
        for headline in snapshot.headlines[:5]:
            symbol = sentiment_symbols.get(headline.sentiment, "?")
            title = headline.title[:70]
            suffix = "..." if len(headline.title) > 70 else ""
            typer.echo(f"  [{symbol}] {title}{suffix}")

    typer.echo(f"\n[Provider: {provider} | Classifier: {classifier}]")


def _display_sentiment_brief(
    snapshot: SentimentSnapshot,
    warning: str | None = None,
) -> None:
    """Display brief sentiment output for --with-sentiment flag.

    Args:
        snapshot: The sentiment snapshot to display
        warning: Optional warning message
    """
    typer.echo(f"\n{'-' * 39}")
    typer.echo("NEWS SENTIMENT")
    typer.echo(f"{'-' * 39}")

    if warning:
        typer.echo(f"\nWarning: {warning}")
        typer.echo("\nNote: Sentiment is contextual information only.")
        typer.echo("      It does NOT affect the risk assessment above.")
        return

    typer.echo(
        f"\nOverall: {snapshot.overall_sentiment.value.upper()} "
        f"({snapshot.total_count} headlines, {snapshot.confidence_pct}%)"
    )
    typer.echo(
        f"\nBreakdown: +{snapshot.positive_count} / "
        f"={snapshot.neutral_count} / -{snapshot.negative_count}"
    )
    typer.echo("\nNote: Sentiment is contextual information only.")
    typer.echo("      It does NOT affect the risk assessment above.")


def _display_ai_explanation(
    ticker: str,
    assessment: "RiskAssessment",
    snapshot: "IndicatorSnapshot",
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> None:
    """Display AI-generated explanation for a risk assessment.

    Handles errors gracefully - displays warning but doesn't crash.

    Args:
        ticker: Stock ticker symbol
        assessment: The risk assessment result
        snapshot: The indicator snapshot
        provider: Optional provider override
        model: Optional model name override (for Ollama)
    """

    typer.echo(f"{'-' * 39}")
    typer.echo("AI EXPLANATION")
    typer.echo(f"{'-' * 39}")

    try:
        # Try to create explainer
        explainer = ExplainerFactory.create(provider=provider, model=model)
        explain_use_case = ExplainRiskUseCase(explainer=explainer)

        explain_response = explain_use_case.execute(
            ExplainRiskRequest(
                ticker=ticker,
                assessment=assessment,
                snapshot=snapshot,
            )
        )

        if explain_response.success:
            typer.echo(f"\n{explain_response.explanation}")
            typer.echo(f"\n[Provider: {explain_response.provider}]")
        else:
            typer.echo(
                f"\nAI explanation unavailable: {explain_response.error_message}",
                err=True,
            )

    except ExplainerAuthError as e:
        typer.echo(f"\nAI explanation unavailable: {e}", err=True)
        typer.echo("Tip: Set the appropriate API key environment variable.", err=True)

    except Exception as e:
        typer.echo(f"\nAI explanation unavailable: {e}", err=True)


@app.command()
def fetch(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history", min=1),
    ] = DEFAULT_DAYS,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", "-r", help="Force refresh from provider (ignore cache)"),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
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
    except ConnectionError:
        typer.echo("Error: Network connection failed.", err=True)
        typer.echo("Tip: Check your internet connection and try again.", err=True)
        raise typer.Exit(1)
    except PermissionError:
        typer.echo(f"Error: Cannot write to database at {resolved_db_path}", err=True)
        typer.echo("Tip: Check file permissions or use --db to specify a different path.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "connection" in error_msg or "network" in error_msg or "timeout" in error_msg:
            typer.echo("Error: Network connection failed.", err=True)
            typer.echo("Tip: Check your internet connection and try again.", err=True)
        elif "no data" in error_msg or "not found" in error_msg:
            typer.echo(f"Error: No market data found for ticker '{ticker.upper()}'", err=True)
            typer.echo(
                "Tip: Verify the ticker symbol is valid for IDX (e.g., BBCA, BBRI, TLKM).",
                err=True,
            )
        else:
            typer.echo(f"Failed to fetch data: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def sma(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="SMA period (number of days)", min=1),
    ] = 20,
    field: Annotated[
        str,
        typer.Option(
            "--field", "-f", help="Price field (open/high/low/close)", callback=validate_field
        ),
    ] = "close",
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history", min=1),
    ] = DEFAULT_DAYS,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
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
            typer.echo("\nSummary:")
            typer.echo(f"  Latest:  {sma_only[-1]:>14.2f}")
            typer.echo(f"  Highest: {max(sma_only):>14.2f}")
            typer.echo(f"  Lowest:  {min(sma_only):>14.2f}")
            avg_sma = sum(sma_only, Decimal("0")) / len(sma_only)
            typer.echo(f"  Average: {avg_sma:>14.2f}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"Error: Database not found at {resolved_db_path}", err=True)
        typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "no such table" in error_msg or "no data" in error_msg:
            typer.echo(f"Error: No cached data found for {ticker.upper()}", err=True)
            typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        else:
            typer.echo(f"Failed to compute SMA: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def ema(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="EMA period (number of days)", min=1),
    ] = 20,
    field: Annotated[
        str,
        typer.Option(
            "--field", "-f", help="Price field (open/high/low/close)", callback=validate_field
        ),
    ] = "close",
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history", min=1),
    ] = DEFAULT_DAYS,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
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
            typer.echo("\nSummary:")
            typer.echo(f"  Latest:  {ema_only[-1]:>14.2f}")
            typer.echo(f"  Highest: {max(ema_only):>14.2f}")
            typer.echo(f"  Lowest:  {min(ema_only):>14.2f}")
            avg_ema = sum(ema_only, Decimal("0")) / len(ema_only)
            typer.echo(f"  Average: {avg_ema:>14.2f}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"Error: Database not found at {resolved_db_path}", err=True)
        typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "no such table" in error_msg or "no data" in error_msg:
            typer.echo(f"Error: No cached data found for {ticker.upper()}", err=True)
            typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        else:
            typer.echo(f"Failed to compute EMA: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def rsi(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="RSI period (number of days)", min=1),
    ] = 14,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history", min=1),
    ] = DEFAULT_DAYS,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
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
            typer.echo("\nSummary:")
            typer.echo(f"  Latest:  {rsi_only[-1]:>10.2f}")
            typer.echo(f"  Highest: {max(rsi_only):>10.2f}")
            typer.echo(f"  Lowest:  {min(rsi_only):>10.2f}")
            avg_rsi = sum(rsi_only, Decimal("0")) / len(rsi_only)
            typer.echo(f"  Average: {avg_rsi:>10.2f}")

            # Overbought/oversold analysis
            latest_rsi = rsi_only[-1]
            if latest_rsi > Decimal("70"):
                typer.echo("\n  Status: OVERBOUGHT (RSI > 70)")
            elif latest_rsi < Decimal("30"):
                typer.echo("\n  Status: OVERSOLD (RSI < 30)")
            else:
                typer.echo("\n  Status: NEUTRAL (30 <= RSI <= 70)")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"Error: Database not found at {resolved_db_path}", err=True)
        typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "no such table" in error_msg or "no data" in error_msg:
            typer.echo(f"Error: No cached data found for {ticker.upper()}", err=True)
            typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        else:
            typer.echo(f"Failed to compute RSI: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def compute(
    indicator: Annotated[str, typer.Argument(help="Indicator name (SMA, RSI, ATR, or custom formula)")],
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    period: Annotated[
        int,
        typer.Option("--period", "-p", help="Period (ignored for formulas)", min=1),
    ] = 14,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Days of data to fetch", min=1),
    ] = DEFAULT_DAYS,
    tail: Annotated[
        int,
        typer.Option("--tail", "-t", help="Show last N values", min=1),
    ] = 30,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
    ] = None,
) -> None:
    """
    Compute any indicator values for a stock.

    Works with built-in indicators (SMA, EMA, RSI), plugins (ATR),
    and custom formulas created via create-indicator.

    Examples:
        saham compute RSI BBCA
        saham compute SMA BBCA --period 50
        saham compute SMOOTH_RSI BBCA --tail 10
        saham compute ATR BBCA --days 180 --tail 50
    """
    # Create registry with plugins and formulas loaded
    registry = create_indicator_registry()
    indicator_upper = indicator.upper()

    if not registry.is_registered(indicator_upper):
        typer.echo(f"Unknown indicator: {indicator}", err=True)
        typer.echo("\nAvailable indicators:")
        for name in sorted(registry.list_indicators()):
            typer.echo(f"  {name}")
        raise typer.Exit(1)

    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Wire up dependencies
    repository = SQLiteMarketRepository(db_path=resolved_db_path)
    candles = repository.get_candles(ticker.upper())

    if not candles:
        typer.echo(f"No data for {ticker.upper()}. Run: saham fetch {ticker.upper()}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Computing {indicator_upper} for {ticker.upper()}...")

    try:
        # Limit candles to requested days (most recent)
        if len(candles) > days:
            candles = candles[-days:]

        values = registry.compute(indicator_upper, candles, period)

        if not values:
            typer.echo(f"Insufficient data to compute {indicator_upper}", err=True)
            raise typer.Exit(1)

        # Limit to tail
        display_values = values[-tail:] if len(values) > tail else values

        # Display header
        typer.echo(f"\nTicker: {ticker.upper()}")
        typer.echo(f"Indicator: {indicator_upper}")

        # Show period only for non-formula indicators
        default_period = registry.get_default_period(indicator_upper)
        if default_period > 0:
            typer.echo(f"Period: {period}")

        typer.echo(f"Values: {len(values)} (showing last {len(display_values)})")

        # Display table
        typer.echo(f"\n{'Date':<12} {indicator_upper:>14}")
        typer.echo("-" * 27)
        for dt, val in display_values:
            typer.echo(f"{dt!s:<12} {val:>14.2f}")

        # Summary
        all_vals = [v for _, v in values]
        typer.echo(f"\nSummary:")
        typer.echo(f"  Latest:  {all_vals[-1]:>14.2f}")
        typer.echo(f"  Highest: {max(all_vals):>14.2f}")
        typer.echo(f"  Lowest:  {min(all_vals):>14.2f}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"Error: Database not found at {resolved_db_path}", err=True)
        typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "no such table" in error_msg or "no data" in error_msg:
            typer.echo(f"Error: No cached data found for {ticker.upper()}", err=True)
            typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        else:
            typer.echo(f"Failed to compute indicator: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def indicators(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    sma_period: Annotated[
        int,
        typer.Option("--sma", help="SMA period (default: 20)", min=1),
    ] = 20,
    ema_period: Annotated[
        int,
        typer.Option("--ema", help="EMA period (default: 20)", min=1),
    ] = 20,
    rsi_period: Annotated[
        int,
        typer.Option("--rsi", help="RSI period (default: 14)", min=1),
    ] = 14,
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days of history", min=1),
    ] = DEFAULT_DAYS,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
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

            typer.echo("\nSummary:")
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
    except FileNotFoundError:
        typer.echo(f"Error: Database not found at {resolved_db_path}", err=True)
        typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "no such table" in error_msg or "no data" in error_msg:
            typer.echo(f"Error: No cached data found for {ticker.upper()}", err=True)
            typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        else:
            typer.echo(f"Failed to compute indicators: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def risk(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            "-p",
            help="Risk profile (conservative/balanced/aggressive)",
            callback=validate_profile,
        ),
    ] = "balanced",
    all_profiles: Annotated[
        bool,
        typer.Option("--all", "-a", help="Show assessment for all profiles"),
    ] = False,
    rules_file: Annotated[
        Optional[Path],
        typer.Option(
            "--rules-file",
            "-r",
            help="Path to custom YAML rules file (overrides --profile)",
        ),
    ] = None,
    sma_period: Annotated[
        int,
        typer.Option("--sma", help="SMA period (default: 20)", min=1),
    ] = 20,
    ema_period: Annotated[
        int,
        typer.Option("--ema", help="EMA period (default: 20)", min=1),
    ] = 20,
    rsi_period: Annotated[
        int,
        typer.Option("--rsi", help="RSI period (default: 14)", min=1),
    ] = 14,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
    ] = None,
    explain: Annotated[
        bool,
        typer.Option("--explain", "-e", help="Generate AI explanation for the assessment"),
    ] = False,
    provider: Annotated[
        Optional[str],
        typer.Option("--provider", help="AI provider (claude/openai/gemini/ollama/mock)"),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Model name for AI provider (e.g., qwen2.5-coder:1.5b)"),
    ] = None,
    with_sentiment: Annotated[
        bool,
        typer.Option("--with-sentiment", "-s", help="Include news sentiment analysis"),
    ] = False,
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

    Custom Rules:
        Use --rules-file to provide a YAML file with custom rules.
        This overrides the --profile option and uses your custom rules instead.
        See config/custom_rules.yaml.example for the YAML schema.

    Requires cached data (run 'saham fetch TICKER' first).

    AI Explanation (optional):
        Use --explain to get AI-generated insights about the assessment.
        Use --provider to override the default AI provider.
        Use --model to specify a model (useful for Ollama).

    Examples:
        saham risk BBCA
        saham risk BBRI --profile conservative
        saham risk TLKM --all
        saham risk BBCA --rules-file config/my_rules.yaml
        saham risk BBCA -r config/custom_rules.yaml
        saham risk BBCA --explain
        saham risk BBCA --explain --provider ollama --model qwen2.5-coder:1.5b
    """
    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Warn if --rules-file used with --all
    if rules_file and all_profiles:
        typer.echo(
            "Warning: --rules-file is incompatible with --all. "
            "Using custom rules for single assessment.",
            err=True,
        )

    # Wire up dependencies
    repository = SQLiteMarketRepository(db_path=resolved_db_path)
    # Create registry with plugins and formulas loaded for custom rules support
    registry = create_indicator_registry()
    use_case = AssessRiskUseCase(repository=repository, registry=registry)

    typer.echo(f"Assessing risk for {ticker.upper()}...")

    try:
        request = AssessRiskRequest(
            ticker=ticker,
            profile=profile,
            sma_period=sma_period,
            ema_period=ema_period,
            rsi_period=rsi_period,
            rules_file=rules_file,
        )

        # Custom rules take precedence over --all
        if all_profiles and not rules_file:
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

            typer.echo("\nIndicators:")
            typer.echo(f"  SMA({response.sma_period}):  {snapshot.sma:>12,.2f}")
            typer.echo(f"  EMA({response.ema_period}):  {snapshot.ema:>12,.2f}")
            typer.echo(f"  RSI({response.rsi_period}):  {snapshot.rsi:>12.2f}")

            typer.echo(f"\n{'-' * 39}")
            typer.echo("RISK ASSESSMENT")
            typer.echo(f"{'-' * 39}")

            typer.echo(f"\nRisk Level:  {assessment.risk_level_name}")
            typer.echo(f"Confidence:  {assessment.confidence}/100")

            typer.echo("\nRationale:")
            for reason in assessment.rationale_list:
                typer.echo(f"  - {reason}")

            typer.echo(f"\n{'-' * 39}")

            # Generate AI explanation if requested (single profile only)
            if explain:
                typer.echo("")  # Blank line before AI section
                _display_ai_explanation(
                    ticker=ticker.upper(),
                    assessment=assessment,
                    snapshot=snapshot,
                    provider=provider,
                    model=model,
                )

        # Warn if --explain used with --all
        if explain and all_profiles:
            typer.echo(
                "\nNote: AI explanation is only available for single profile view. "
                "Run without --all to get AI explanation.",
                err=True,
            )

        # Display sentiment if requested
        if with_sentiment:
            try:
                news_provider = SentimentFactory.create_news_provider()
                classifier = SentimentFactory.create_classifier(use_ai=False)
                sentiment_use_case = FetchSentimentUseCase(
                    news_provider=news_provider,
                    classifier=classifier,
                )
                sentiment_response = sentiment_use_case.execute(
                    FetchSentimentRequest(ticker=ticker)
                )
                _display_sentiment_brief(
                    snapshot=sentiment_response.snapshot,
                    warning=sentiment_response.warning,
                )
            except Exception as e:
                typer.echo(f"\n{'-' * 39}")
                typer.echo("NEWS SENTIMENT")
                typer.echo(f"{'-' * 39}")
                typer.echo(f"\nWarning: Could not fetch sentiment: {e}", err=True)
                typer.echo("\nNote: Sentiment is contextual information only.")
                typer.echo("      It does NOT affect the risk assessment above.")

        typer.echo("\nDISCLAIMER: Analysis only, not trading advice.")

    except RulesFileError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except RulesSchemaError as e:
        typer.echo(f"Error in rules file: {e}", err=True)
        raise typer.Exit(1)
    except RulesValidationError as e:
        typer.echo(f"Invalid rules: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"Error: Database not found at {resolved_db_path}", err=True)
        typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "no such table" in error_msg or "no data" in error_msg:
            typer.echo(f"Error: No cached data found for {ticker.upper()}", err=True)
            typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        else:
            typer.echo(f"Failed to assess risk: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def backtest(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    strategy: Annotated[
        Optional[str],
        typer.Option(
            "--strategy",
            "-S",
            help="Strategy name or path (e.g., 'momentum' or './strategies/momentum/strategy.yaml')",
        ),
    ] = None,
    rules_file: Annotated[
        Optional[Path],
        typer.Option(
            "--rules-file",
            "-r",
            help="Path to YAML rules file (backward-compatible alias for --strategy)",
        ),
    ] = None,
    start: Annotated[
        Optional[str],
        typer.Option(
            "--start",
            "-s",
            help="Start date (YYYY-MM-DD)",
        ),
    ] = None,
    end: Annotated[
        Optional[str],
        typer.Option(
            "--end",
            "-e",
            help="End date (YYYY-MM-DD)",
        ),
    ] = None,
    capital: Annotated[
        int,
        typer.Option(
            "--capital",
            "-c",
            help="Initial capital in IDR (default: 100,000,000)",
            min=1,
        ),
    ] = 100_000_000,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Show detailed trade-by-trade output",
        ),
    ] = False,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Path to SQLite database (default: ./data.db)"),
    ] = None,
) -> None:
    """
    Backtest a strategy against historical data.

    Runs a deterministic backtest simulation using rules from a YAML file
    or strategy package. Replays historical candles chronologically and
    applies rules per candle to generate hypothetical entry/exit signals.

    Strategy Resolution:
        --strategy can be a strategy name (e.g., 'momentum') or an explicit path.
        Strategy names are searched in:
        1. ./NAME/strategy.yaml
        2. ./strategies/NAME/strategy.yaml
        3. ./strategies/NAME/strategy.yaml

    Requires cached data (run 'saham fetch TICKER' first).

    Signal Mapping (customizable in YAML):
        LOW_RISK  -> ENTER_LONG (buy)
        MODERATE  -> HOLD (maintain position)
        HIGH_RISK -> EXIT_LONG (sell)

    Examples:
        saham backtest BBCA --strategy momentum
        saham backtest BBCA -S ./strategies/momentum/strategy.yaml
        saham backtest BBCA --rules-file config/custom_rules.yaml.example
        saham backtest BBRI -S momentum --start 2024-01-01
        saham backtest TLKM -S momentum --capital 50000000 --verbose
    """
    from datetime import datetime

    # Validate that either --strategy or --rules-file is provided
    if not strategy and not rules_file:
        typer.echo("Error: Either --strategy or --rules-file is required.", err=True)
        typer.echo("")
        typer.echo("Examples:", err=True)
        typer.echo("  saham backtest BBCA --strategy momentum", err=True)
        typer.echo("  saham backtest BBCA --rules-file config/rules.yaml", err=True)
        raise typer.Exit(1)

    # Resolve configuration
    resolved_db_path = db_path or DEFAULT_DB_PATH

    # Parse dates
    start_date = None
    end_date = None
    try:
        if start:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
        if end:
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        typer.echo("Error: Invalid date format. Use YYYY-MM-DD.", err=True)
        raise typer.Exit(1)

    # Resolve strategy path
    # --strategy takes precedence over --rules-file
    resolved_rules_path: Path
    strategy_display: str

    if strategy:
        # Use StrategyLoader to resolve strategy name or path
        registry = create_indicator_registry()
        loader = StrategyLoader(registry=registry)
        try:
            resolved_rules_path = loader.resolve(strategy)
            strategy_display = strategy
        except StrategyNotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
    else:
        # Use rules_file directly (backward compatible)
        resolved_rules_path = rules_file  # type: ignore
        strategy_display = str(rules_file)

    typer.echo(f"Backtesting {ticker.upper()} with {strategy_display}...")

    try:
        # Wire up dependencies
        repository = SQLiteMarketRepository(db_path=resolved_db_path)
        # Create registry with plugins and formulas loaded for custom indicator support
        # Note: registry may already be created above for strategy resolution
        if not strategy:
            registry = create_indicator_registry()
        use_case = BacktestUseCase(repository=repository, registry=registry)

        # Execute use case
        request = BacktestRequest(
            ticker=ticker,
            rules_file=resolved_rules_path,
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal(str(capital)),
        )
        response = use_case.execute(request)
        result = response.result

        # Display results
        typer.echo("")
        typer.echo("=" * 50)
        typer.echo("BACKTEST RESULTS")
        typer.echo("=" * 50)
        typer.echo("")
        typer.echo(f"Ticker:         {result.ticker}")
        typer.echo(f"Strategy:       {result.strategy_name}")
        typer.echo(f"Period:         {result.start_date} to {result.end_date}")

        typer.echo("")
        typer.echo("-" * 50)
        typer.echo("PERFORMANCE")
        typer.echo("-" * 50)
        typer.echo("")
        typer.echo(f"Initial Capital:     {result.initial_capital:>18,.0f} IDR")
        typer.echo(f"Final Capital:       {result.final_capital:>18,.0f} IDR")
        typer.echo(f"Total Return:        {result.total_return_pct:>18.2f}%")
        typer.echo(f"Max Drawdown:        {result.max_drawdown_pct:>18.2f}%")

        typer.echo("")
        typer.echo("-" * 50)
        typer.echo("TRADE STATISTICS")
        typer.echo("-" * 50)
        typer.echo("")
        typer.echo(f"Total Trades:        {result.trade_count:>18}")
        typer.echo(f"Winning Trades:      {result.winning_trades:>18}")
        typer.echo(f"Losing Trades:       {result.losing_trades:>18}")
        typer.echo(f"Win Rate:            {result.win_rate:>18.2f}%")
        typer.echo(f"Profit Factor:       {result.profit_factor:>18.2f}")

        if result.trades:
            typer.echo(f"Avg Win:             {result.avg_win:>18,.0f} IDR")
            typer.echo(f"Avg Loss:            {result.avg_loss:>18,.0f} IDR")

        typer.echo("")
        typer.echo("=" * 50)

        # Verbose mode: show individual trades
        if verbose and result.trades:
            typer.echo("")
            typer.echo("TRADE HISTORY")
            typer.echo("-" * 80)
            typer.echo(
                f"{'#':<4} {'Entry':<12} {'Exit':<12} {'Entry Price':>12} "
                f"{'Exit Price':>12} {'P&L':>14} {'%':>8}"
            )
            typer.echo("-" * 80)

            for i, trade in enumerate(result.trades, 1):
                pnl_sign = "+" if trade.pnl >= 0 else ""
                typer.echo(
                    f"{i:<4} {str(trade.entry_date):<12} {str(trade.exit_date):<12} "
                    f"{trade.entry_price:>12,.0f} {trade.exit_price:>12,.0f} "
                    f"{pnl_sign}{trade.pnl:>13,.0f} {trade.pnl_percent:>7.2f}%"
                )

            typer.echo("-" * 80)
            typer.echo(f"\nEntry Rules: {', '.join(set(t.entry_rule for t in result.trades))}")
            typer.echo(f"Exit Rules:  {', '.join(set(t.exit_rule for t in result.trades))}")

        typer.echo("\nDISCLAIMER: Historical simulation only, not trading advice.")

    except StrategyNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except RulesFileError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except RulesSchemaError as e:
        typer.echo(f"Error in rules file: {e}", err=True)
        raise typer.Exit(1)
    except RulesValidationError as e:
        typer.echo(f"Invalid rules: {e}", err=True)
        raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo(f"Error: Database not found at {resolved_db_path}", err=True)
        typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "no such table" in error_msg or "no data" in error_msg:
            typer.echo(f"Error: No cached data found for {ticker.upper()}", err=True)
            typer.echo(f"Tip: Run 'saham fetch {ticker.upper()}' first to download data.", err=True)
        else:
            typer.echo(f"Failed to run backtest: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def sentiment(
    ticker: Annotated[str, typer.Argument(help="Stock ticker symbol (e.g., BBCA)")],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Days of news to fetch", min=1, max=30),
    ] = 3,
    max_headlines: Annotated[
        int,
        typer.Option("--max", help="Maximum headlines to analyze", min=1, max=50),
    ] = 20,
    ai_classify: Annotated[
        bool,
        typer.Option("--ai-classify", help="Use AI for classification (requires API key)"),
    ] = False,
    provider: Annotated[
        Optional[str],
        typer.Option(
            "--provider", help="AI provider for classification (claude/openai/gemini/ollama)"
        ),
    ] = None,
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Model name for AI provider"),
    ] = None,
) -> None:
    """
    Fetch and analyze news sentiment for an IDX stock.

    Retrieves recent news headlines and classifies them as positive,
    neutral, or negative using keyword matching (default) or AI.

    Sentiment is informational only and does NOT affect risk assessment.

    Classifier modes:
    - keyword (default): Rule-based, uses Indonesian + English keywords
    - AI (--ai-classify): Uses LLM for more nuanced classification

    Examples:
        saham sentiment BBCA
        saham sentiment BBRI --days 7
        saham sentiment TLKM --ai-classify
        saham sentiment ASII --ai-classify --provider ollama --model llama3
    """
    typer.echo(f"Fetching news sentiment for {ticker.upper()}...")

    try:
        # Wire up dependencies
        news_provider = SentimentFactory.create_news_provider()
        classifier = SentimentFactory.create_classifier(
            use_ai=ai_classify,
            provider=provider,
            model=model,
        )
        use_case = FetchSentimentUseCase(
            news_provider=news_provider,
            classifier=classifier,
        )

        # Execute use case
        request = FetchSentimentRequest(
            ticker=ticker,
            max_headlines=max_headlines,
            days=days,
        )
        response = use_case.execute(request)

        # Display header
        typer.echo(f"\nTicker: {response.ticker}")
        typer.echo(f"Date: {response.snapshot.fetch_date}")
        typer.echo(f"Headlines Analyzed: {response.snapshot.total_count}")

        # Display sentiment
        _display_sentiment_full(
            snapshot=response.snapshot,
            provider=response.provider,
            classifier=response.classifier,
            warning=response.warning,
        )

        typer.echo("\nDISCLAIMER: Sentiment analysis only, not trading advice.")

    except Exception as e:
        error_msg = str(e).lower()
        if "connection" in error_msg or "network" in error_msg or "timeout" in error_msg:
            typer.echo("Warning: Could not fetch news (network issue).", err=True)
            typer.echo("Tip: Check your internet connection and try again.", err=True)
        else:
            typer.echo(f"Failed to analyze sentiment: {e}", err=True)
        raise typer.Exit(1)


@app.command("create-indicator")
def create_indicator(
    intent: Annotated[
        str, typer.Argument(help="Natural language description of the indicator")
    ],
    name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Indicator name (e.g., SMOOTH_RSI)"),
    ] = None,
    provider: Annotated[
        str,
        typer.Option("--provider", "-p", help="AI provider (claude/openai/gemini/ollama/mock)"),
    ] = "mock",
    model: Annotated[
        Optional[str],
        typer.Option("--model", "-m", help="Model name for AI provider"),
    ] = None,
    save: Annotated[
        bool,
        typer.Option("--save/--no-save", help="Save formula to storage"),
    ] = True,
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas", help="Path to formulas file"),
    ] = None,
) -> None:
    """
    Create a custom indicator from natural language description.

    Uses AI to translate natural language into a formula expression,
    validates the formula, and optionally saves it for reuse.

    AI Providers:
    - mock: Local mock (no API key needed, for testing)
    - claude: Anthropic Claude (requires ANTHROPIC_API_KEY)
    - openai: OpenAI GPT (requires OPENAI_API_KEY)
    - gemini: Google Gemini (requires GOOGLE_API_KEY)
    - ollama: Local Ollama (requires running Ollama server)

    Examples:
        saham create-indicator "smoothed RSI with 14 period" --name SMOOTH_RSI
        saham create-indicator "MACD line" --name MACD --provider claude
        saham create-indicator "14-day RSI" --no-save
    """
    typer.echo(f"Translating: {intent!r}")
    typer.echo(f"Provider: {provider}")

    try:
        # Create registry to get available functions
        registry = create_indicator_registry()
        available_functions = registry.get_available_indicators()

        # Create translator adapter
        translator = FormulaTranslatorAdapter(provider=provider, model=model)

        # Create and execute use case
        use_case = CreateIndicatorFromIntentUseCase(
            translator=translator,
            available_functions=available_functions,
        )

        request = CreateIndicatorFromIntentRequest(
            intent=intent,
            indicator_name=name,
        )
        response = use_case.execute(request)

        # Handle result
        if response.unsupported:
            typer.echo("\nThis intent cannot be expressed as a formula.", err=True)
            typer.echo(
                "Tip: Try describing a mathematical combination of indicators.",
                err=True,
            )
            raise typer.Exit(1)

        if not response.success:
            typer.echo(f"\nError: {response.error_message}", err=True)
            raise typer.Exit(1)

        # Success
        typer.echo(f"\nFormula: {response.formula}")

        # Generate name if not provided
        indicator_name = name
        if not indicator_name:
            # Generate from formula (simple heuristic)
            formula_clean = response.formula.replace("(", "_").replace(")", "")
            formula_clean = formula_clean.replace(",", "_").replace(" ", "")
            indicator_name = f"CUSTOM_{formula_clean[:20]}".upper()
            typer.echo(f"Auto-generated name: {indicator_name}")

        indicator_name = indicator_name.upper()

        # Register in memory
        if response.ast:
            try:
                registry.register_formula(indicator_name, response.ast)
                typer.echo(f"Registered: {indicator_name}")
            except Exception as e:
                typer.echo(f"Warning: Could not register formula: {e}", err=True)

        # Save to storage
        if save and response.formula:
            resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
            storage = FormulaStorage(path=resolved_path)

            try:
                storage.save(
                    name=indicator_name,
                    formula=response.formula,
                    intent=intent,
                )
                typer.echo(f"Saved to: {resolved_path}")
            except FormulaStorageError as e:
                typer.echo(f"Warning: Could not save formula: {e}", err=True)

        typer.echo(f"\nYou can now use {indicator_name} in risk rules or backtest.")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        error_msg = str(e).lower()
        if "api key" in error_msg or "authentication" in error_msg:
            typer.echo(f"Error: {e}", err=True)
            typer.echo(
                f"Tip: Set the appropriate API key environment variable for {provider}.",
                err=True,
            )
        elif "connection" in error_msg or "timeout" in error_msg:
            typer.echo("Error: Could not connect to AI provider.", err=True)
            if provider == "ollama":
                typer.echo("Tip: Ensure Ollama is running: ollama serve", err=True)
            else:
                typer.echo("Tip: Check your internet connection.", err=True)
        else:
            typer.echo(f"Failed to create indicator: {e}", err=True)
        raise typer.Exit(1)


@app.command("list-indicators")
def list_indicators(
    show_formulas: Annotated[
        bool,
        typer.Option("--formulas", "-f", help="Show formula expressions"),
    ] = False,
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas-file", help="Path to formulas file"),
    ] = None,
) -> None:
    """
    List all available indicators.

    Shows built-in indicators, loaded plugins, and custom formulas.
    Use --formulas to see the formula expressions for custom indicators.

    Examples:
        saham list-indicators
        saham list-indicators --formulas
    """
    # Load registry with plugins
    registry = create_indicator_registry()

    # Load stored formulas
    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)
    stored_formulas = storage.load_all()

    # Built-in indicators
    from src.application.services.indicator_registry import BUILTIN_NAMES

    typer.echo("\nBuilt-in Indicators:")
    typer.echo("-" * 40)
    builtin_descriptions = {
        "SMA": "Simple Moving Average",
        "EMA": "Exponential Moving Average",
        "RSI": "Relative Strength Index",
    }
    for name in sorted(BUILTIN_NAMES):
        desc = builtin_descriptions.get(name, "")
        period = registry.get_default_period(name)
        typer.echo(f"  {name:<12} {desc:<30} (period: {period})")

    # Plugin indicators
    plugin_names = set(registry.list_indicators()) - BUILTIN_NAMES - set(registry.list_formulas())
    if plugin_names:
        typer.echo("\nPlugin Indicators:")
        typer.echo("-" * 40)
        for name in sorted(plugin_names):
            period = registry.get_default_period(name)
            typer.echo(f"  {name:<12} (period: {period})")

    # Custom formulas
    if stored_formulas:
        typer.echo("\nCustom Formulas:")
        typer.echo("-" * 40)
        for name, stored in sorted(stored_formulas.items()):
            if show_formulas:
                typer.echo(f"  {name:<12} = {stored.formula}")
            else:
                typer.echo(f"  {name:<12}")

        typer.echo(f"\nFormulas file: {resolved_path}")
    else:
        typer.echo("\nNo custom formulas saved.")
        typer.echo("Tip: Use 'saham create-indicator' to create custom indicators.")

    typer.echo(f"\nTotal available: {len(registry.list_indicators()) + len(stored_formulas)}")


@app.command("show-formula")
def show_formula(
    name: Annotated[str, typer.Argument(help="Formula name")],
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas-file", help="Path to formulas file"),
    ] = None,
) -> None:
    """
    Show details of a saved formula.

    Displays the formula expression, original intent, and creation date.

    Examples:
        saham show-formula SMOOTH_RSI
        saham show-formula MACD
    """
    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)

    stored = storage.get(name)
    if stored is None:
        typer.echo(f"Formula '{name.upper()}' not found.", err=True)
        typer.echo("\nAvailable formulas:")
        for formula_name in storage.list_names():
            typer.echo(f"  {formula_name}")
        raise typer.Exit(1)

    typer.echo(f"\nName:    {stored.name}")
    typer.echo(f"Formula: {stored.formula}")
    if stored.intent:
        typer.echo(f"Intent:  {stored.intent}")
    typer.echo(f"Created: {stored.created.strftime('%Y-%m-%d %H:%M:%S')}")


@app.command("delete-indicator")
def delete_indicator(
    name: Annotated[str, typer.Argument(help="Formula name to delete")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompt"),
    ] = False,
    formulas_path: Annotated[
        Optional[Path],
        typer.Option("--formulas-file", help="Path to formulas file"),
    ] = None,
) -> None:
    """
    Delete a saved custom formula.

    Removes the formula from persistent storage. Built-in and plugin
    indicators cannot be deleted.

    Examples:
        saham delete-indicator SMOOTH_RSI
        saham delete-indicator MACD --force
    """
    name_upper = name.upper()

    # Check if built-in
    from src.application.services.indicator_registry import BUILTIN_NAMES

    if name_upper in BUILTIN_NAMES:
        typer.echo(f"Cannot delete built-in indicator: {name_upper}", err=True)
        raise typer.Exit(1)

    resolved_path = formulas_path or DEFAULT_FORMULAS_PATH
    storage = FormulaStorage(path=resolved_path)

    # Check if exists
    if not storage.exists(name_upper):
        typer.echo(f"Formula '{name_upper}' not found in storage.", err=True)
        raise typer.Exit(1)

    # Confirm deletion
    if not force:
        stored = storage.get(name_upper)
        typer.echo(f"\nFormula to delete:")
        typer.echo(f"  Name:    {stored.name}")
        typer.echo(f"  Formula: {stored.formula}")

        confirm = typer.confirm("\nDelete this formula?")
        if not confirm:
            typer.echo("Cancelled.")
            raise typer.Exit(0)

    # Delete
    try:
        deleted = storage.delete(name_upper)
        if deleted:
            typer.echo(f"Deleted {name_upper} from storage.")
        else:
            typer.echo(f"Formula '{name_upper}' not found.", err=True)
            raise typer.Exit(1)
    except FormulaStorageError as e:
        typer.echo(f"Failed to delete formula: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def version() -> None:
    """
    Show version and build information.

    Displays the current version of the saham CLI and basic build info.
    """
    typer.echo(f"saham v{__version__}")
    typer.echo("Local-first stock analysis CLI for Indonesia Stock Exchange (IDX)")
    typer.echo("")
    typer.echo("For help:  saham --help")
    typer.echo("For docs:  https://github.com/anthropics/ai-saham")


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
