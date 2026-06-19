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

from src.adapters.cli.broker_display import (
    display_broker_flow,
    display_broker_history,
    display_broker_top,
    display_broker_top_foreign_snapshots,
    display_foreign_top_scan,
    display_history_fetch_preview,
    display_import_preview,
    display_recent_fetch_summary,
    format_value,
)
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
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)

# Supported providers
PROVIDERS = ("idx", "stockbit-session")
DEFAULT_PROVIDER = "idx"

_DEFAULT_PROFILE_DIR = Path(".stockbit_profile")


def _create_provider(provider_name: str) -> BrokerDataProvider:
    """Create a broker data provider by name."""
    if provider_name == "idx":
        return IdxBrokerDataProvider()
    elif provider_name == "stockbit-session":
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        return StockbitPlaywrightBrokerProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name}. Choose from: {', '.join(PROVIDERS)}")

# Default configuration
DEFAULT_DB_PATH = Path("data.db")
DEFAULT_DAYS = 30


def broker_status() -> None:
    """
    Check broker data provider status.

    Shows status of all available providers.
    """
    # IDX provider (always available)
    typer.echo("IDX provider: " + typer.style("Available", fg=typer.colors.GREEN)
               + " (public API, no auth required)")

    # Stockbit Playwright session provider
    try:
        from src.infrastructure.browser.playwright_stockbit import StockbitPlaywrightBrokerProvider
        session_provider = StockbitPlaywrightBrokerProvider()
        if session_provider.is_authenticated():
            marker = _DEFAULT_PROFILE_DIR / ".logged_in_at"
            age_h: float | None = None
            if marker.exists():
                import time as _time
                try:
                    age_h = round((_time.time() - float(marker.read_text())) / 3600, 1)
                except Exception:
                    pass
            age_str = f" ({age_h}h old)" if age_h is not None else ""
            typer.echo(
                "Stockbit-Session provider: "
                + typer.style(f"Active{age_str}", fg=typer.colors.GREEN)
                + " — use --provider stockbit-session"
            )
        else:
            typer.echo(
                "Stockbit-Session provider: "
                + typer.style("No session", fg=typer.colors.YELLOW)
                + " (run 'saham fetch stockbit login' to set up)"
            )
    except ImportError:
        typer.echo(
            "Stockbit-Session provider: "
            + typer.style("playwright not installed", fg=typer.colors.YELLOW)
        )

    typer.echo(f"\nDefault provider: {DEFAULT_PROVIDER}")


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
        stockbit-session - Stockbit browser session (run 'saham fetch stockbit login')

    Examples:
        saham fetch broker BBCA                       # IDX provider (default)
        saham fetch broker BBCA --provider stockbit-session
        saham fetch broker BBCA --days 90             # Last 90 days
        saham fetch broker BBCA --refresh             # Force refresh
        saham fetch broker BBCA -s 2024-01-01 -e 2024-06-30
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

    from src.infrastructure.browser.stockbit_market_time import (
        format_market_status_line,
        get_display_market_status,
    )
    typer.echo(format_market_status_line(get_display_market_status()))
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

        # For Stockbit providers, also fetch exact historical foreign flow
        # (avg_price) so the daily foreign-flow series is complete.
        if not response.from_cache and provider_name == "stockbit-session":
            points = provider.fetch_foreign_flow_history(ticker, days=days)
            if points:
                repository.save_foreign_flow_points(points)
                typer.echo(typer.style(f"Saved {len(points)} exact foreign-flow points", fg=typer.colors.CYAN))

        display_recent_fetch_summary(response.summaries)

    except BrokerDataAuthError as e:
        typer.echo(typer.style(f"Auth error: {e}", fg=typer.colors.RED))
        typer.echo("Run: saham fetch stockbit login")
        raise typer.Exit(1)
    except BrokerDataProviderError as e:
        typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED))
        raise typer.Exit(1)


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
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
) -> None:
    """
    Show foreign flow summary for a stock.

    Displays cached broker data. Use 'saham fetch broker' first to load data.

    Example:
        saham view broker flow BBCA --days 20
        saham view broker flow BBCA --format json
    """
    repository = SQLiteBrokerRepository(db_path)
    use_case = GetBrokerDataUseCase(repository)

    end_date = date.today()
    start_date = end_date - timedelta(days=days + 10)  # Extra buffer for weekends

    summaries = use_case.execute(ticker, start_date, end_date)

    if not summaries:
        typer.echo(
            typer.style("No data found. ", fg=typer.colors.YELLOW)
            + f"Run 'saham fetch broker {ticker}' first."
        )
        raise typer.Exit(1)

    # Take last N days
    summaries = summaries[-days:]

    if fmt == "json":
        import json as _json
        typer.echo(_json.dumps([s.to_dict() for s in summaries], indent=2, default=str))
        return

    display_broker_flow(ticker, summaries)


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
        saham view broker top BBCA
        saham view broker top BBCA --date 2024-01-15
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
                + f"Run 'saham fetch broker {ticker}' first."
            )
            raise typer.Exit(1)
        summary = summaries[-1]

    if not summary:
        typer.echo(typer.style("No data for that date.", fg=typer.colors.YELLOW))
        raise typer.Exit(1)

    display_broker_top(ticker, summary)


def broker_history_view(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g. BBCA)")],
    days: Annotated[
        int,
        typer.Option("--days", help="How many recent trading days to show", min=1, max=365),
    ] = 30,
    source: Annotated[
        str,
        typer.Option("--source", help="Cached source to read: stockbit, idx, or auto"),
    ] = "auto",
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path"),
    ] = Path("data/broker_data.db"),
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
) -> None:
    """
    Show cached daily foreign broker flow history for a stock.

    This is a read-only view of data already stored by 'saham fetch broker-history'
    or market refresh commands. It never calls remote providers.

    Examples:
        saham view broker history BBCA --days 30
        saham view broker history BBCA --source stockbit --format json
    """
    selected_source = None if source == "auto" else source
    if source not in {"auto", "stockbit", "idx"}:
        typer.echo(typer.style("Unknown source. Use: auto, stockbit, or idx", fg=typer.colors.RED))
        raise typer.Exit(1)

    repo = SQLiteBrokerRepository(db_path)
    points = repo.get_foreign_flow_points(ticker, source=selected_source)
    if not points:
        typer.echo(
            typer.style("No cached history found. ", fg=typer.colors.YELLOW)
            + f"Run 'saham fetch broker-history {ticker.upper()}' first."
        )
        raise typer.Exit(1)

    points = points[-days:]
    if fmt == "json":
        import json as _json
        payload = [
            {
                "ticker": p.ticker,
                "date": p.date.isoformat(),
                "source": p.source,
                "net_val": str(p.net_val),
                "net_lot": p.net_lot,
                "avg_price": str(p.avg_price),
            }
            for p in points
        ]
        typer.echo(_json.dumps(payload, indent=2))
        return
    if fmt != "table":
        typer.echo(typer.style("Unknown format. Use: table or json", fg=typer.colors.RED))
        raise typer.Exit(1)

    display_broker_history(ticker, points)


def broker_top_foreign_view(
    snapshot_date: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Snapshot date (YYYY-MM-DD), default: today"),
    ] = None,
    days: Annotated[
        int,
        typer.Option("--days", help="Cached look-back window used by fetch", min=1, max=365),
    ] = 7,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max stocks to show", min=1, max=50),
    ] = 20,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path"),
    ] = Path("data/broker_data.db"),
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
) -> None:
    """
    Show cached foreign-broker top stock snapshots.

    This is a read-only view of data already stored by
    'saham fetch broker-top-foreign'. It never calls remote providers.

    Examples:
        saham view broker top-foreign --days 7
        saham view broker top-foreign --date 2024-01-15 --limit 10
    """
    query_date = date.fromisoformat(snapshot_date) if snapshot_date else date.today()
    repo = SQLiteBrokerRepository(db_path)
    snapshots = repo.get_foreign_flow_snapshots(query_date, period_days=days)
    if not snapshots:
        typer.echo(
            typer.style("No cached top-foreign snapshot found. ", fg=typer.colors.YELLOW)
            + "Run 'saham fetch broker-top-foreign' first."
        )
        raise typer.Exit(1)

    snapshots = snapshots[:limit]
    if fmt == "json":
        import json as _json
        payload = [
            {
                "ticker": s.ticker,
                "snapshot_date": query_date.isoformat(),
                "period_days": days,
                "net_val": str(s.net_val),
                "net_lot": s.net_lot,
                "direction": "buy" if s.is_accumulating else "sell",
            }
            for s in snapshots
        ]
        typer.echo(_json.dumps(payload, indent=2))
        return
    if fmt != "table":
        typer.echo(typer.style("Unknown format. Use: table or json", fg=typer.colors.RED))
        raise typer.Exit(1)

    display_broker_top_foreign_snapshots(
        snapshots=snapshots,
        query_date=query_date,
        days=days,
    )


def broker_top_foreign(
    days: Annotated[
        int,
        typer.Option("--days", help="Look-back window in days (1/3/7/30/90/365)", min=1, max=365),
    ] = 7,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Max stocks to return", min=1, max=50),
    ] = 20,
    provider: Annotated[
        str,
        typer.Option("--provider", help="Provider: stockbit-session"),
    ] = "stockbit-session",
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path"),
    ] = Path("data/broker_data.db"),
    no_save: Annotated[
        bool,
        typer.Option("--no-save", help="Do not persist results to database"),
    ] = False,
) -> None:
    """
    Show which stocks foreign brokers are most actively buying/selling.

    Calls the broker-centric Stockbit Exodus API to scan the universe:
    given 10 known foreign broker codes, returns the stocks they traded
    most in the period. Useful as a complementary screening signal to IEV.

    Results are automatically saved to the database for later querying.
    Requires an active Stockbit browser session (run 'saham fetch stockbit login' first).

    Examples:
        saham fetch broker-top-foreign
        saham fetch broker-top-foreign --days 7 --limit 20
        saham fetch broker-top-foreign --days 365
    """
    prov = _create_provider(provider)
    if not prov.is_authenticated():
        typer.echo(
            typer.style("Not authenticated.", fg=typer.colors.RED)
            + " Run: saham fetch stockbit login"
        )
        raise typer.Exit(1)

    end = date.today()
    start = end - timedelta(days=days)

    from src.infrastructure.browser.stockbit_market_time import (
        format_market_status_line,
        get_display_market_status,
    )
    typer.echo("")
    typer.echo(format_market_status_line(get_display_market_status()))
    typer.echo(f"Foreign broker accumulation scan ({start} → {end})")
    typer.echo("─" * 55)

    try:
        snapshots = prov.fetch_foreign_top_stocks(start, end, limit=limit)
    except Exception as e:
        typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
        raise typer.Exit(1)

    if not snapshots:
        typer.echo(typer.style("No data returned.", fg=typer.colors.YELLOW))
        typer.echo("Run: saham fetch stockbit spy --target broker-scan")
        return

    # Auto-save to database
    if not no_save:
        try:
            repo = SQLiteBrokerRepository(db_path)
            repo.save_foreign_flow_snapshots(snapshots, snapshot_date=end, period_days=days)
            typer.echo(typer.style(f"  Saved {len(snapshots)} snapshots → {db_path}", fg=typer.colors.CYAN))
        except Exception as e:
            typer.echo(typer.style(f"  Warning: could not save to DB: {e}", fg=typer.colors.YELLOW), err=True)

    display_foreign_top_scan(snapshots)

    typer.echo("")
    typer.echo(f"Showing {len(snapshots)} stocks. Use --limit to adjust.")


def broker_history(
    ticker: Annotated[str, typer.Argument(help="Stock ticker (e.g. BBCA)")],
    days: Annotated[
        int,
        typer.Option("--days", help="How many trading days to fetch (1–365)", min=1, max=365),
    ] = 365,
    provider: Annotated[
        str,
        typer.Option("--provider", help="Provider: stockbit-session"),
    ] = "stockbit-session",
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path"),
    ] = Path("data/broker_data.db"),
) -> None:
    """
    Fetch and store daily foreign broker flow history for a stock (time-series).

    Unlike 'saham fetch broker' (which stores full broker breakdown), this command
    fetches the lightweight daily net-flow time-series with exact avg_price
    from Stockbit's historical endpoint. Ideal for backtesting and trend analysis.

    Results are stored in the foreign-flow time-series table with source='stockbit'.

    Examples:
        saham fetch broker-history BBCA
        saham fetch broker-history BBCA --days 30
    """
    prov = _create_provider(provider)
    if not prov.is_authenticated():
        typer.echo(
            typer.style("Not authenticated.", fg=typer.colors.RED)
            + " Run: saham fetch stockbit login"
        )
        raise typer.Exit(1)

    ticker = ticker.upper()
    typer.echo(f"\nFetching {days}-day flow history for {ticker}...")

    try:
        points = prov.fetch_foreign_flow_history(ticker, days=days)
    except Exception as e:
        typer.echo(typer.style(f"Error: {e}", fg=typer.colors.RED), err=True)
        raise typer.Exit(1)

    if not points:
        typer.echo(typer.style("No historical data returned.", fg=typer.colors.YELLOW))
        return

    repo = SQLiteBrokerRepository(db_path)
    repo.save_foreign_flow_points(points)

    typer.echo(typer.style(f"Saved {len(points)} foreign-flow points for {ticker} → {db_path}", fg=typer.colors.GREEN))

    display_history_fetch_preview(ticker, points)


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
        saham fetch broker-import data.csv                  # Auto-detect format
        saham fetch broker-import data.csv --preview        # Preview without saving
        saham fetch broker-import data.csv --mapping rti    # Use custom mapping
        saham fetch broker-import data.csv --on-error fail  # Stop on first error
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
            display_import_preview(response)

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


def broker_mappings() -> None:
    """
    List available CSV mapping configurations.

    Mappings define how CSV columns map to expected fields.
    Create custom mappings in config/csv_mappings/
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
    typer.echo(f"\nUse with: saham fetch broker-import data.csv --mapping <name>")
    typer.echo(f"Custom mappings: config/csv_mappings/<name>.yaml")
