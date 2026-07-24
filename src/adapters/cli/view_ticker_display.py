"""
show_ticker_view — read-only ticker information dashboard.

Loads a cache-only dashboard via GetTickerDashboardUseCase, then renders
Rich panels or JSON. Does NOT trigger network fetch.

Layer: Adapter
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.text import Text

from src.adapters.cli.rich_display import console
from src.adapters.cli.view_ticker_events_display import _corp_action_panel, _sentiment_panel
from src.adapters.cli.view_ticker_flow_display import (
    _bandar_panel,
    _foreign_flow_panel,
    _insider_panel,
)
from src.adapters.cli.view_ticker_identity_display import (
    _freshness_panel,
    _identity_panel,
    _profile_panel,
)
from src.adapters.cli.view_ticker_json import ticker_dashboard_to_json_dict
from src.adapters.cli.view_ticker_market_activity_display import (
    _candles_panel,
    _iev_panel,
    _price_structure_panel,
    _seasonality_panel,
)
from src.adapters.cli.view_ticker_valuation_display import (
    _analyst_panel,
    _earnings_panel,
    _ownership_panel,
    _valuation_panel,
)
from src.application.dto.ticker_dashboard import GetTickerDashboardRequest, TickerDashboard

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

    _render_ticker_dashboard_table(dashboard)


def _render_ticker_dashboard_table(dashboard: TickerDashboard) -> None:
    """Pure table renderer over an assembled TickerDashboard DTO."""
    panels = set(dashboard.panel_keys)
    fetch_hint = dashboard.fetch_hint
    brief = dashboard.mode == "brief"

    c = console()
    c.print()
    if "identity" in panels:
        c.print(_identity_panel(dashboard.ticker, dashboard.notation, empty_hint=fetch_hint))
    if "freshness" in panels:
        c.print(
            _freshness_panel(
                dashboard.ticker,
                list(dashboard.freshness),
                as_of=dashboard.as_of,
            )
        )
    if "valuation" in panels:
        c.print(
            _valuation_panel(
                dashboard.fundamentals,
                dashboard.forward_estimates,
                dashboard.latest_close,
            )
        )
    if "price_structure" in panels:
        c.print(_price_structure_panel(dashboard.price_structure, empty_hint=fetch_hint))
    if "analyst" in panels:
        c.print(_analyst_panel(dashboard.analyst, empty_hint=fetch_hint))
    if "earnings" in panels:
        c.print(_earnings_panel(list(dashboard.earnings), empty_hint=fetch_hint))
    if "ownership" in panels:
        c.print(_ownership_panel(dashboard.ownership, empty_hint=fetch_hint))
    if "bandar" in panels:
        c.print(_bandar_panel(dashboard.bandar, empty_hint=fetch_hint))
    if "foreign_flow" in panels:
        c.print(
            _foreign_flow_panel(
                list(dashboard.foreign_flow_points),
                source=dashboard.foreign_flow_source,
                empty_hint=fetch_hint,
            )
        )
    if "corp_actions" in panels:
        c.print(
            _corp_action_panel(
                list(dashboard.corp_actions),
                status=dashboard.corp_status,
                empty_hint=fetch_hint,
            )
        )
    if "insider" in panels:
        c.print(
            _insider_panel(
                list(dashboard.insider_txns),
                status=dashboard.insider_status,
                last_known=dashboard.insider_last_known,
                empty_hint=fetch_hint,
            )
        )
    if "seasonality" in panels:
        c.print(
            _seasonality_panel(
                dashboard.seasonality,
                dashboard.today.month,
                empty_hint=fetch_hint,
            )
        )
    if "iev" in panels:
        c.print(_iev_panel(list(dashboard.iev_rows), empty_hint=fetch_hint))
    if "sentiment" in panels:
        c.print(_sentiment_panel(list(dashboard.sentiment_logs), empty_hint=fetch_hint))
    if "profile" in panels:
        c.print(_profile_panel(dashboard.profile, empty_hint=fetch_hint))
    if "candles" in panels:
        c.print(_candles_panel(list(dashboard.candles), empty_hint=fetch_hint))
    mode_note = "brief mode · " if brief else ""
    c.print(
        Text(
            f"  {mode_note}Run `{fetch_hint}` to refresh stale or missing data.",
            style="dim",
        )
    )
    if dashboard.related_actions:
        c.print(Text("  Deep-dives:", style="dim"))
        for action in dashboard.related_actions:
            c.print(Text(f"    {action.command}", style="dim"))
    c.print()
