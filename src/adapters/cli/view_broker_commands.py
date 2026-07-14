"""
CLI commands for viewing broker data.

Provides commands to view broker summary, configuration, and flow statistics.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_broker_display import (
    display_broker_flow,
    display_broker_history,
    display_broker_top,
    display_broker_top_foreign_snapshots,
)
from src.application.use_case.fetch_broker_data_use_case import (
    GetBrokerDataUseCase,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.csv import MappingLoader
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)
DEFAULT_PROVIDER = APP_CFG.broker.provider
PROVIDERS = ("idx", "stockbit")


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
    ] = APP_CFG.analysis.format,
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
    ] = DEFAULT_DB_PATH,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
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
    ] = DEFAULT_DB_PATH,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
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
    typer.echo("\nUse with: saham fetch broker-import data.csv --mapping <name>")
    typer.echo("Custom mappings: config/csv_mappings/<name>.yaml")
