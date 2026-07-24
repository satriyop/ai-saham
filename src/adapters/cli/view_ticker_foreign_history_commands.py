"""
CLI: view ticker foreign-history — foreign_flow_points series for a stock.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.view_ticker_contract_cli import (
    echo_json,
    exit_missing_ticker_data,
    resolve_output_format,
)
from src.adapters.cli.view_ticker_foreign_history_display import (
    display_ticker_foreign_history,
)
from src.application.dto.view_ticker_contract import (
    ViewResultStatus,
    ViewWindow,
    build_view_envelope,
)
from src.application.use_case.view_ticker_foreign_history_use_case import (
    ViewTickerForeignHistoryRequest,
)
from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps
from src.infrastructure.config.app_config import load_app_config


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
    output_format = resolve_output_format(fmt or cfg.analysis.format)

    if source not in {"auto", "stockbit", "idx"}:
        typer.echo(
            typer.style("Unknown source. Use: auto, stockbit, or idx", fg=typer.colors.RED),
            err=True,
        )
        raise typer.Exit(2)

    deps = build_view_ticker_deps(db_path)
    try:
        result = deps.foreign_history.execute(
            ViewTickerForeignHistoryRequest(ticker=ticker, days=days, source=source)
        )
    except ValueError as exc:
        typer.echo(typer.style(str(exc), fg=typer.colors.RED), err=True)
        raise typer.Exit(2) from exc

    if result is None:
        exit_missing_ticker_data(
            ticker=ticker,
            what="foreign flow history",
            source="foreign_flow_points",
            fetch_hint=f"saham fetch broker-history {ticker.upper()}",
        )

    if output_format == "json":
        echo_json(
            build_view_envelope(
                subject_id=result.ticker,
                verb="foreign-history",
                status=ViewResultStatus.OK,
                as_of=result.as_of,
                window=ViewWindow(days=result.days),
                source=result.resolved_source,
                scope="full",
                fetch_hint=result.fetch_hint,
                data={
                    "requested_source": result.requested_source,
                    "resolved_source": result.resolved_source,
                    "points": [
                        {
                            "ticker": p.ticker,
                            "date": p.date.isoformat(),
                            "source": p.source,
                            "net_val": str(p.net_val),
                            "net_lot": p.net_lot,
                            "avg_price": str(p.avg_price),
                        }
                        for p in result.points
                    ],
                },
            )
        )
        return

    display_ticker_foreign_history(result.ticker, list(result.points))
