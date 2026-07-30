"""Plain-text ticker dashboard for multi-surface (TUI detail / capture).

Uses the same panel composition as ``saham view ticker show`` table mode.
Panel widgets remain CLI Rich modules; this shared entry is the only
surface-facing formatter TUI may call (ADR-045: no TUI→CLI display import).

Layer: Adapter (shared presentation facade)
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.text import Text

from src.application.dto.ticker_dashboard import TickerDashboard


def format_ticker_dashboard_text(dashboard: TickerDashboard, *, width: int = 100) -> str:
    """Same CLI table panels as plain text (for TUI detail stage / capture)."""
    buf = StringIO()
    out = Console(
        file=buf,
        width=width,
        highlight=False,
        force_terminal=True,
        color_system=None,
    )
    render_ticker_dashboard_table(dashboard, out=out)
    return buf.getvalue()


def render_ticker_dashboard_table(
    dashboard: TickerDashboard,
    *,
    out: Console | None = None,
) -> None:
    """Pure table renderer over an assembled TickerDashboard DTO."""
    # Local import keeps panel modules out of module import graph for light tests.
    from src.adapters.cli.rich_display import console
    from src.adapters.cli.screen_accum_sector_macro_display import build_sector_macro_panel
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

    panels = set(dashboard.panel_keys)
    fetch_hint = dashboard.fetch_hint
    brief = dashboard.mode == "brief"

    c = out if out is not None else console()
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
    if "sector_macro" in panels:
        smc_panel = build_sector_macro_panel(
            dashboard.sector_macro_context_evidence,
            ticker=dashboard.ticker,
            surface="view",
        )
        if smc_panel is not None:
            c.print(smc_panel)
        elif dashboard.sector_macro_context_evidence is None:
            # Fail-soft empty: still signal the panel slot when full mode lists it
            # but loader returned None without a panel_error (unmapped / soft fail).
            from src.adapters.cli.rich_display import panel as _panel

            c.print(
                _panel(
                    Text(
                        "Sector macro unavailable (unmapped, missing series, "
                        "or no local macro-calendar).\n"
                        "  DIAGNOSTIC — no scoring impact (ADR-053).\n"
                        f"  Judgment: saham screen accum {dashboard.ticker}",
                        style="dim",
                    ),
                    title="SECTOR MACRO",
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
