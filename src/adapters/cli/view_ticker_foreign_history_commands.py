"""
CLI: view ticker foreign-history — foreign_flow_points series for a stock.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_ticker_foreign_history_display import (
    display_ticker_foreign_history,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_broker_repository import (
    SQLiteBrokerRepository,
)


def ticker_foreign_history(
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
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    fmt: Annotated[
        Optional[str],
        typer.Option("--format", help="Output format: table or json"),
    ] = None,
) -> None:
    """
    Show cached daily foreign net flow history for a stock.

    Reads foreign_flow_points only (not local desk rows). Data from
    'saham fetch broker-history' or market refresh. Never calls remote providers.

    Examples:
        saham view ticker foreign-history BBCA --days 30
        saham view ticker foreign-history BBCA --source stockbit --format json
    """
    cfg = load_app_config()
    db_path = db_path or Path(cfg.storage.db_path)
    fmt = fmt or cfg.analysis.format
    selected_source = None if source == "auto" else source
    if source not in {"auto", "stockbit", "idx"}:
        typer.echo(
            typer.style("Unknown source. Use: auto, stockbit, or idx", fg=typer.colors.RED)
        )
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

    display_ticker_foreign_history(ticker, points)
