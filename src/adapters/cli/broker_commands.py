"""
CLI commands for broker data management.

Provides commands to fetch broker summary, configure auth, view foreign flow,
and import broker data from CSV files.

Layer: Adapter
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.fetch_broker_data import (
    FetchBrokerDataRequest,
    FetchBrokerDataUseCase,
    GetBrokerDataUseCase,
)
from src.application.use_case.import_broker_data import (
    ImportBrokerDataRequest,
    ImportBrokerDataUseCase,
)
from src.domain.ports.broker_data_provider import (
    BrokerDataAuthError,
    BrokerDataProvider,
    BrokerDataProviderError,
)
from src.domain.ports.csv_broker_parser import (
    CsvBrokerParserError,
    ErrorStrategy,
)
from src.infrastructure.csv import BrokerCsvAdapter, MappingLoader
from src.infrastructure.data_providers.idx import IdxBrokerDataProvider
from src.infrastructure.data_providers.stockbit import (
    StockbitBrokerDataProvider,
    validate_token,
)
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)

# Supported providers
PROVIDERS = ("idx", "stockbit")
DEFAULT_PROVIDER = "idx"


def _create_provider(provider_name: str) -> BrokerDataProvider:
    """Create a broker data provider by name."""
    if provider_name == "idx":
        return IdxBrokerDataProvider()
    elif provider_name == "stockbit":
        return StockbitBrokerDataProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}. Choose from: {', '.join(PROVIDERS)}")

# Create Typer sub-app for broker commands
broker_app = typer.Typer(
    name="broker",
    help="Manage broker flow data (fetch, auth, view)",
    no_args_is_help=True,
)

# Default configuration
DEFAULT_DB_PATH = Path.home() / ".ai-saham" / "data.db"
DEFAULT_DAYS = 30


def format_value(value: Decimal) -> str:
    """Format large numbers for display (B/M/K)."""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


@broker_app.command("auth")
def broker_auth(
    token: Annotated[
        str,
        typer.Argument(
            help="Stockbit JWT token from browser DevTools"
        ),
    ],
    validate: Annotated[
        bool,
        typer.Option(
            "--validate/--no-validate",
            help="Validate token before saving",
        ),
    ] = True,
) -> None:
    """
    Configure Stockbit authentication token.

    To get your token:
    1. Login to stockbit.com in your browser
    2. Open DevTools (F12) -> Network tab
    3. Click any stock ticker (e.g., BBCA)
    4. Filter for "exodus" requests
    5. Copy the Bearer token from Authorization header

    Token expires in ~24 hours and needs to be refreshed.

    Example:
        saham broker auth "eyJhbGci..."
    """
    if validate:
        typer.echo("Validating token...")
        if not validate_token(token):
            typer.echo(
                typer.style("Token validation failed. ", fg=typer.colors.RED)
                + "The token may be expired or invalid."
            )
            raise typer.Exit(1)
        typer.echo(typer.style("Token is valid!", fg=typer.colors.GREEN))

    # Save token
    provider = StockbitBrokerDataProvider()
    provider.save_token(token)
    typer.echo(f"Token saved to ~/.ai-saham/stockbit_token.json")


@broker_app.command("status")
def broker_status() -> None:
    """
    Check broker data provider status.

    Shows status of all available providers.
    """
    # IDX provider (always available)
    typer.echo("IDX provider: " + typer.style("Available", fg=typer.colors.GREEN)
               + " (public API, no auth required)")

    # Stockbit provider (needs token)
    stockbit = StockbitBrokerDataProvider()
    if stockbit.is_authenticated():
        typer.echo("Stockbit provider: " + typer.style("Configured", fg=typer.colors.GREEN))

        typer.echo("  Validating Stockbit token...")
        try:
            summary = stockbit.fetch_broker_summary("BBCA", date.today())
            if summary:
                typer.echo(
                    "  " + typer.style("Status: ", fg=typer.colors.GREEN)
                    + "Connected and working"
                )
            else:
                typer.echo(
                    "  " + typer.style("Status: ", fg=typer.colors.YELLOW)
                    + "Connected (no data for today yet)"
                )
        except BrokerDataAuthError:
            typer.echo(
                "  " + typer.style("Token expired or invalid. ", fg=typer.colors.RED)
                + "Please get a new token from stockbit.com"
            )
        except BrokerDataProviderError as e:
            typer.echo(
                "  " + typer.style("Connection error: ", fg=typer.colors.RED)
                + str(e)
            )
    else:
        typer.echo(
            "Stockbit provider: " + typer.style("Not configured", fg=typer.colors.YELLOW)
            + " (run 'saham broker auth <token>' to set up)"
        )

    typer.echo(f"\nDefault provider: {DEFAULT_PROVIDER}")


@broker_app.command("fetch")
def broker_fetch(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to fetch"),
    ] = DEFAULT_DAYS,
    start: Annotated[
        Optional[str],
        typer.Option("--start", "-s", help="Start date (YYYY-MM-DD)"),
    ] = None,
    end: Annotated[
        Optional[str],
        typer.Option("--end", "-e", help="End date (YYYY-MM-DD)"),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", "-r", help="Force refresh from provider"),
    ] = False,
    provider_name: Annotated[
        str,
        typer.Option(
            "--provider", "-P",
            help=f"Data provider ({', '.join(PROVIDERS)})",
        ),
    ] = DEFAULT_PROVIDER,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Database path"),
    ] = DEFAULT_DB_PATH,
) -> None:
    """
    Fetch broker summary data for a stock.

    Fetches broker flow data and caches locally.
    Subsequent calls use cached data unless --refresh is specified.

    Providers:
        idx       - IDX public API (default, no auth required)
        stockbit  - Stockbit API (requires auth token)

    Examples:
        saham broker fetch BBCA                       # IDX provider (default)
        saham broker fetch BBCA --provider stockbit   # Stockbit provider
        saham broker fetch BBCA --days 90             # Last 90 days
        saham broker fetch BBCA --refresh             # Force refresh
        saham broker fetch BBCA -s 2024-01-01 -e 2024-06-30
    """
    # Validate provider
    if provider_name not in PROVIDERS:
        typer.echo(
            typer.style(f"Unknown provider: {provider_name}", fg=typer.colors.RED)
        )
        typer.echo(f"Available providers: {', '.join(PROVIDERS)}")
        raise typer.Exit(1)

    # Parse dates
    if start:
        start_date = date.fromisoformat(start)
    else:
        start_date = date.today() - timedelta(days=days)

    if end:
        end_date = date.fromisoformat(end)
    else:
        end_date = date.today()

    typer.echo(f"Fetching broker data for {ticker.upper()}...")
    typer.echo(f"Provider: {provider_name} | Date range: {start_date} to {end_date}")

    # Initialize dependencies
    provider = _create_provider(provider_name)
    repository = SQLiteBrokerRepository(db_path)
    use_case = FetchBrokerDataUseCase(provider, repository)

    try:
        response = use_case.execute(
            FetchBrokerDataRequest(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                refresh=refresh,
            )
        )

        source = "cache" if response.from_cache else provider_name
        typer.echo(
            typer.style(f"Loaded {len(response.summaries)} days from {source}",
                       fg=typer.colors.GREEN)
        )

        # Show summary
        if response.summaries:
            total_foreign_flow = sum(
                s.foreign_net_value for s in response.summaries
            )
            typer.echo(f"\nTotal foreign net flow: {format_value(total_foreign_flow)}")

            # Show last 5 days
            typer.echo("\nRecent foreign flow:")
            for summary in response.summaries[-5:]:
                flow = summary.foreign_net_value
                color = typer.colors.GREEN if flow > 0 else typer.colors.RED
                typer.echo(
                    f"  {summary.date}: "
                    + typer.style(format_value(flow), fg=color)
                )

    except BrokerDataAuthError as e:
        typer.echo(typer.style(f"Auth error: {e}", fg=typer.colors.RED))
        typer.echo("Run 'saham broker auth <token>' to set your token.")
        raise typer.Exit(1)
    except BrokerDataProviderError as e:
        typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED))
        raise typer.Exit(1)


@broker_app.command("flow")
def broker_flow(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to show"),
    ] = 10,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Database path"),
    ] = DEFAULT_DB_PATH,
) -> None:
    """
    Show foreign flow summary for a stock.

    Displays cached broker data. Use 'broker fetch' first to load data.

    Example:
        saham broker flow BBCA --days 20
    """
    repository = SQLiteBrokerRepository(db_path)
    use_case = GetBrokerDataUseCase(repository)

    end_date = date.today()
    start_date = end_date - timedelta(days=days + 10)  # Extra buffer for weekends

    summaries = use_case.execute(ticker, start_date, end_date)

    if not summaries:
        typer.echo(
            typer.style("No data found. ", fg=typer.colors.YELLOW)
            + f"Run 'saham broker fetch {ticker}' first."
        )
        raise typer.Exit(1)

    # Take last N days
    summaries = summaries[-days:]

    typer.echo(f"\nForeign Flow for {ticker.upper()} (last {len(summaries)} trading days)")
    typer.echo("=" * 60)

    # Calculate stats
    total_flow = sum(s.foreign_net_value for s in summaries)
    buy_days = sum(1 for s in summaries if s.is_foreign_accumulating)
    sell_days = len(summaries) - buy_days

    # Consecutive count
    consecutive = 0
    for s in reversed(summaries):
        if s.is_foreign_accumulating:
            consecutive += 1
        else:
            break

    typer.echo(f"Total net flow: {format_value(total_flow)}")
    typer.echo(f"Buy days: {buy_days} | Sell days: {sell_days}")
    typer.echo(f"Consecutive buy days: {consecutive}")
    typer.echo("-" * 60)

    # Daily breakdown
    typer.echo(f"{'Date':<12} {'Net Flow':>12} {'Ratio':>8} {'Top Buyer':>10} {'Top Seller':>10}")
    typer.echo("-" * 60)

    for summary in summaries:
        flow = summary.foreign_net_value
        ratio = summary.foreign_flow_ratio
        color = typer.colors.GREEN if flow > 0 else typer.colors.RED

        top_buyer = summary.top_buyers[0].broker_code if summary.top_buyers else "-"
        top_seller = summary.top_sellers[0].broker_code if summary.top_sellers else "-"

        typer.echo(
            f"{summary.date.isoformat():<12} "
            + typer.style(f"{format_value(flow):>12}", fg=color)
            + f" {ratio:>7.1f}%"
            + f" {top_buyer:>10}"
            + f" {top_seller:>10}"
        )


@broker_app.command("top")
def broker_top(
    ticker: Annotated[
        str,
        typer.Argument(help="Stock ticker symbol (e.g., BBCA)"),
    ],
    target_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Date (YYYY-MM-DD), default: latest"),
    ] = None,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Database path"),
    ] = DEFAULT_DB_PATH,
) -> None:
    """
    Show top brokers for a stock on a specific date.

    Example:
        saham broker top BBCA
        saham broker top BBCA --date 2024-01-15
    """
    repository = SQLiteBrokerRepository(db_path)

    if target_date:
        query_date = date.fromisoformat(target_date)
        summary = repository.get_broker_summary(ticker, query_date)
    else:
        # Get latest
        summaries = repository.get_broker_summaries(ticker)
        if not summaries:
            typer.echo(
                typer.style("No data found. ", fg=typer.colors.YELLOW)
                + f"Run 'saham broker fetch {ticker}' first."
            )
            raise typer.Exit(1)
        summary = summaries[-1]

    if not summary:
        typer.echo(typer.style("No data for that date.", fg=typer.colors.YELLOW))
        raise typer.Exit(1)

    typer.echo(f"\nBroker Summary for {ticker.upper()} on {summary.date}")
    typer.echo("=" * 70)

    # Foreign flow
    flow = summary.foreign_net_value
    color = typer.colors.GREEN if flow > 0 else typer.colors.RED
    typer.echo(
        f"Foreign Net Flow: "
        + typer.style(format_value(flow), fg=color)
        + f" ({summary.foreign_flow_ratio:.1f}%)"
    )
    typer.echo(f"Total Value: {format_value(summary.total_value)}")
    typer.echo("-" * 70)

    # Top buyers
    typer.echo("\nTop Buyers:")
    typer.echo(f"{'Code':<6} {'Name':<20} {'Type':<8} {'Net Value':>14} {'Net Lot':>10}")
    for b in summary.top_buyers[:5]:
        type_str = "Foreign" if b.is_foreign else "Local"
        typer.echo(
            f"{b.broker_code:<6} "
            f"{b.broker_name[:20]:<20} "
            f"{type_str:<8} "
            + typer.style(f"{format_value(b.net_value):>14}", fg=typer.colors.GREEN)
            + f" {b.net_lot:>10,}"
        )

    # Top sellers
    typer.echo("\nTop Sellers:")
    typer.echo(f"{'Code':<6} {'Name':<20} {'Type':<8} {'Net Value':>14} {'Net Lot':>10}")
    for s in summary.top_sellers[:5]:
        type_str = "Foreign" if s.is_foreign else "Local"
        typer.echo(
            f"{s.broker_code:<6} "
            f"{s.broker_name[:20]:<20} "
            f"{type_str:<8} "
            + typer.style(f"{format_value(s.net_value):>14}", fg=typer.colors.RED)
            + f" {s.net_lot:>10,}"
        )


@broker_app.command("import")
def broker_import(
    file_path: Annotated[
        Path,
        typer.Argument(
            help="Path to CSV file to import",
            exists=True,
            readable=True,
        ),
    ],
    preview: Annotated[
        bool,
        typer.Option(
            "--preview",
            "-p",
            help="Preview import without saving",
        ),
    ] = False,
    mapping: Annotated[
        Optional[str],
        typer.Option(
            "--mapping",
            "-m",
            help="Custom mapping name or YAML file path",
        ),
    ] = None,
    on_error: Annotated[
        str,
        typer.Option(
            "--on-error",
            help="Error handling: skip (default), fail, report",
        ),
    ] = "skip",
    db_path: Annotated[
        Path,
        typer.Option("--db", help="Database path"),
    ] = DEFAULT_DB_PATH,
) -> None:
    """
    Import broker flow data from a CSV file.

    Supports auto-detection of CSV format based on column headers:

    \b
    Simple format (aggregate foreign flow):
      date,ticker,foreign_buy_value,foreign_sell_value,foreign_buy_lot,
      foreign_sell_lot,total_value,total_lot

    \b
    Detailed format (broker transactions):
      date,ticker,broker_code,broker_name,broker_type,buy_lot,sell_lot,
      buy_value,sell_value

    Examples:
        saham broker import data.csv                  # Auto-detect format
        saham broker import data.csv --preview        # Preview without saving
        saham broker import data.csv --mapping rti    # Use custom mapping
        saham broker import data.csv --on-error fail  # Stop on first error
    """
    # Parse error strategy
    error_strategies = {
        "skip": ErrorStrategy.SKIP,
        "fail": ErrorStrategy.FAIL,
        "report": ErrorStrategy.REPORT,
    }
    if on_error not in error_strategies:
        typer.echo(
            typer.style(f"Invalid --on-error value: {on_error}", fg=typer.colors.RED)
        )
        typer.echo(f"Valid values: {', '.join(error_strategies.keys())}")
        raise typer.Exit(1)

    error_strategy = error_strategies[on_error]

    # Load custom mapping if specified
    mapping_config = None
    if mapping:
        mapping_loader = MappingLoader()
        try:
            # Check if it's a file path
            mapping_path = Path(mapping)
            if mapping_path.exists():
                mapping_config = mapping_loader.load_from_file(mapping_path)
            else:
                mapping_config = mapping_loader.load(mapping)
            typer.echo(f"Using mapping: {mapping_config.name}")
        except CsvBrokerParserError as e:
            typer.echo(typer.style(f"Mapping error: {e}", fg=typer.colors.RED))
            raise typer.Exit(1)

    # Initialize dependencies
    parser = BrokerCsvAdapter()
    repository = SQLiteBrokerRepository(db_path)
    use_case = ImportBrokerDataUseCase(parser, repository)

    # Create request
    request = ImportBrokerDataRequest(
        file_path=file_path,
        preview_only=preview,
        error_strategy=error_strategy,
        mapping=mapping_config,
    )

    try:
        # Execute import
        if preview:
            typer.echo(f"Previewing {file_path.name}...")
        else:
            typer.echo(f"Importing {file_path.name}...")

        response = use_case.execute(request)

        # Display format detected
        typer.echo(f"Format detected: {response.format_detected.value}")

        # Preview mode output
        if preview:
            typer.echo("\n" + typer.style("Preview Results", bold=True))
            typer.echo("-" * 60)

            if response.summaries:
                # Show preview data
                typer.echo(f"{'Date':<12} {'Ticker':<8} {'Foreign Net':>14} {'Total Value':>14}")
                typer.echo("-" * 60)

                for summary in response.summaries:
                    flow = summary.foreign_net_value
                    color = typer.colors.GREEN if flow > 0 else typer.colors.RED
                    typer.echo(
                        f"{summary.date.isoformat():<12} "
                        f"{summary.ticker:<8} "
                        + typer.style(f"{format_value(flow):>14}", fg=color)
                        + f" {format_value(summary.total_value):>14}"
                    )

                typer.echo("-" * 60)
                typer.echo(
                    f"Showing {len(response.summaries)} of {response.total_rows} rows"
                )

            if response.errors:
                typer.echo(
                    f"\n{typer.style('Errors:', fg=typer.colors.YELLOW)} "
                    f"{len(response.errors)} rows with issues"
                )
                for error in response.errors[:3]:
                    typer.echo(f"  - {error}")
                if len(response.errors) > 3:
                    typer.echo(f"  ... and {len(response.errors) - 3} more")

            typer.echo("\nRun without --preview to import data.")

        # Import mode output
        else:
            if response.success:
                typer.echo(
                    typer.style(
                        f"\nImported {response.imported_count} broker summaries",
                        fg=typer.colors.GREEN,
                    )
                )

                # Show summary stats
                if response.summaries:
                    tickers = sorted(set(s.ticker for s in response.summaries))
                    dates = sorted(s.date for s in response.summaries)

                    typer.echo(f"Tickers: {', '.join(tickers)}")
                    if len(dates) > 1:
                        typer.echo(f"Date range: {dates[0]} to {dates[-1]}")
                    else:
                        typer.echo(f"Date: {dates[0]}")

                if response.skipped_count > 0:
                    typer.echo(
                        typer.style(
                            f"Skipped {response.skipped_count} invalid rows",
                            fg=typer.colors.YELLOW,
                        )
                    )
            else:
                typer.echo(
                    typer.style(f"\nImport failed: {response.message}", fg=typer.colors.RED)
                )
                raise typer.Exit(1)

            # Show errors if using report strategy
            if response.errors and error_strategy == ErrorStrategy.REPORT:
                typer.echo(f"\n{typer.style('Parse Errors:', fg=typer.colors.YELLOW)}")
                for error in response.errors[:10]:
                    typer.echo(f"  - {error}")
                if len(response.errors) > 10:
                    typer.echo(f"  ... and {len(response.errors) - 10} more")

    except CsvBrokerParserError as e:
        typer.echo(typer.style(f"Parse error: {e}", fg=typer.colors.RED))
        raise typer.Exit(1)


@broker_app.command("mappings")
def broker_mappings() -> None:
    """
    List available CSV mapping configurations.

    Mappings define how CSV columns map to expected fields.
    Create custom mappings in ~/.ai-saham/csv_mappings/ or config/csv_mappings/
    """
    loader = MappingLoader()
    mappings = loader.list_available()

    typer.echo("Available CSV Mappings:")
    typer.echo("-" * 40)

    for name in mappings:
        if name == "default":
            typer.echo(f"  {name} (built-in auto-detection)")
        else:
            typer.echo(f"  {name}")

    typer.echo("-" * 40)
    typer.echo(f"\nUse with: saham broker import data.csv --mapping <name>")
    typer.echo(f"Custom mappings: ~/.ai-saham/csv_mappings/<name>.yaml")
