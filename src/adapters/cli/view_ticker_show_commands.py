"""
CLI: view ticker show — stock dashboard.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.cli_errors import (
    raise_data_unavailable,
    raise_user_error,
    resolve_cli_db_path,
)
from src.infrastructure.config.app_config import load_app_config


def _dashboard_has_cache(dashboard) -> bool:
    """True when at least one critical cache panel has data."""
    return bool(
        dashboard.candles
        or dashboard.notation
        or dashboard.latest_close is not None
        or dashboard.profile
        or dashboard.bandar
        or dashboard.foreign_flow_points
        or dashboard.price_structure is not None
    )


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
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """Show a read-only cached-data dashboard for one ticker.

    Shorthand: `saham view BBCA` is equivalent to `saham view ticker show BBCA`.
    """
    from src.adapters.cli.view_ticker_display import render_ticker_dashboard
    from src.application.dto.ticker_dashboard import GetTickerDashboardRequest
    from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps

    cfg = load_app_config()
    resolved_db = resolve_cli_db_path(db_path, configured_default=cfg.storage.db_path)
    fmt = (output_format or "table").lower()
    if fmt not in {"table", "json"}:
        raise_user_error("Invalid --format. Choose from: table, json")

    symbol = ticker.upper()
    deps = build_view_ticker_deps(resolved_db)
    dashboard = deps.dashboard.execute(GetTickerDashboardRequest(ticker=symbol, brief=brief))

    if not _dashboard_has_cache(dashboard):
        raise_data_unavailable(
            f"No cached data found for {symbol}",
            tip=dashboard.fetch_hint
            or f"Run 'saham fetch market {symbol} --days 365' first to download data.",
        )

    render_ticker_dashboard(dashboard, output_format=fmt)
