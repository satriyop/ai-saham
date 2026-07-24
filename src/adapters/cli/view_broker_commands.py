"""
Broker view subgroup registration — desk axis + meta utilities.

Desk deep-dives: show | top-stocks | flow | history
Meta: status | top-foreign | mappings | list

Stock deep-dives moved to `view ticker …` (clean break).

Layer: Adapter
"""

from __future__ import annotations

import typer

from src.adapters.cli.view_broker_desk_commands import (
    broker_desk_flow,
    broker_desk_history,
    broker_desk_show,
    broker_desk_top_stocks,
)
from src.adapters.cli.view_broker_list_commands import broker_list
from src.adapters.cli.view_broker_mappings_commands import broker_mappings
from src.adapters.cli.view_broker_status_commands import broker_status
from src.adapters.cli.view_broker_top_foreign_commands import broker_top_foreign_view

broker_view_app = typer.Typer(
    name="broker",
    help=(
        "Desk-centric views and broker meta utilities.\n\n"
        "Desk: `show|top-stocks|flow|history <CODE>` (tracked only).\n"
        "Universe: `top-foreign`. Meta: `status`, `mappings`, `list`.\n"
        "Stock broker deep-dives: `saham view ticker top-brokers|flow|…`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

broker_view_app.command("show")(broker_desk_show)
broker_view_app.command("top-stocks")(broker_desk_top_stocks)
broker_view_app.command("flow")(broker_desk_flow)
broker_view_app.command("history")(broker_desk_history)
broker_view_app.command("status")(broker_status)
broker_view_app.command("top-foreign")(broker_top_foreign_view)
broker_view_app.command("mappings")(broker_mappings)
broker_view_app.command("list")(broker_list)

__all__ = ["broker_view_app"]
