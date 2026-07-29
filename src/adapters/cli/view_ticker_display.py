"""
show_ticker_view — read-only ticker information dashboard.

Loads a cache-only dashboard via GetTickerDashboardUseCase, then renders
Rich panels or JSON. Does NOT trigger network fetch.

Layer: Adapter
"""

from __future__ import annotations

import json
from pathlib import Path

from src.adapters.cli.rich_display import console
from src.adapters.cli.view_ticker_json import ticker_dashboard_to_json_dict
from src.adapters.shared.view_ticker_dashboard_text import (
    format_ticker_dashboard_text,
    render_ticker_dashboard_table,
)
from src.application.dto.ticker_dashboard import GetTickerDashboardRequest, TickerDashboard

__all__ = [
    "DEFAULT_DB_PATH",
    "show_ticker_view",
    "render_ticker_dashboard",
    "format_ticker_dashboard_text",
    "render_ticker_dashboard_table",
    "_render_ticker_dashboard_table",
]

DEFAULT_DB_PATH = Path("data.db")


def show_ticker_view(
    ticker: str,
    db_path: Path = DEFAULT_DB_PATH,
    *,
    brief: bool = False,
    output_format: str = "table",
) -> None:
    """Render a read-only dashboard of all cached data for ticker."""
    from src.infrastructure.composition.view_ticker_deps import build_view_ticker_deps

    deps = build_view_ticker_deps(Path(db_path))
    dashboard = deps.dashboard.execute(
        GetTickerDashboardRequest(ticker=ticker.upper(), brief=brief)
    )
    render_ticker_dashboard(dashboard, output_format=output_format)


def render_ticker_dashboard(
    dashboard: TickerDashboard,
    *,
    output_format: str = "table",
) -> None:
    """Render an already-assembled dashboard as table or JSON."""
    fmt = (output_format or "table").lower()
    if fmt not in {"table", "json"}:
        raise ValueError(f"Unsupported output format: {output_format!r}")

    if fmt == "json":
        print(json.dumps(ticker_dashboard_to_json_dict(dashboard), indent=2, default=str))
        return

    render_ticker_dashboard_table(dashboard, out=console())


# Backward-compatible alias used by older tests.
_render_ticker_dashboard_table = render_ticker_dashboard_table
