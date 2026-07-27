"""
Ticker view subgroup registration and facade.

Stock deep-dives: show | top-brokers | flow | foreign-history | distribution |
financials

Layer: Adapter
"""

from __future__ import annotations

import typer

from src.adapters.cli.view_ticker_distribution_commands import ticker_distribution
from src.adapters.cli.view_ticker_financials_commands import ticker_financials
from src.adapters.cli.view_ticker_flow_commands import ticker_flow
from src.adapters.cli.view_ticker_foreign_history_commands import ticker_foreign_history
from src.adapters.cli.view_ticker_show_commands import ticker_show
from src.adapters.cli.view_ticker_top_brokers_commands import ticker_top_brokers

ticker_view_app = typer.Typer(
    name="ticker",
    help=(
        "Stock deep-dives and dashboard.\n\n"
        "Overview: `saham view BBCA` or `saham view ticker show BBCA`.\n"
        "Deep-dives: top-brokers | flow | foreign-history | distribution | "
        "financials."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

ticker_view_app.command("show")(ticker_show)
ticker_view_app.command("top-brokers")(ticker_top_brokers)
ticker_view_app.command("flow")(ticker_flow)
ticker_view_app.command("foreign-history")(ticker_foreign_history)
ticker_view_app.command("distribution")(ticker_distribution)
ticker_view_app.command("financials")(ticker_financials)

__all__ = ["ticker_view_app"]
