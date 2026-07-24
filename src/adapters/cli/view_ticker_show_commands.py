"""
CLI: view ticker show — stock dashboard.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.infrastructure.config.app_config import load_app_config


def ticker_show(
    ticker: Annotated[str, typer.Argument(help="Ticker symbol (e.g. BBCA)")],
    brief: Annotated[
        bool,
        typer.Option(
            "--brief",
            help="Show a compact decision-relevant subset of panels.",
        ),
    ] = False,
    output_format: Annotated[
        Optional[str],
        typer.Option(
            "--format",
            help="Output format: table (default) or json.",
        ),
    ] = None,
) -> None:
    """Show a read-only cached-data dashboard for one ticker.

    Shorthand: `saham view BBCA` is equivalent to `saham view ticker show BBCA`.
    """
    from src.adapters.cli.view_ticker_display import show_ticker_view

    cfg = load_app_config()
    fmt = (output_format or "table").lower()
    if fmt not in {"table", "json"}:
        typer.echo("Invalid --format. Choose from: table, json", err=True)
        raise typer.Exit(1)

    show_ticker_view(
        ticker.upper(),
        db_path=Path(cfg.storage.db_path),
        brief=brief,
        output_format=fmt,
    )
