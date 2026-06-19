"""
Read-only data browsing commands.

Layer: Adapter
"""

import typer

from src.adapters.cli.broker_commands import (
    broker_flow,
    broker_mappings,
    broker_status,
    broker_top,
)

view_app = typer.Typer(
    name="view",
    help="Read-only data browsing — inspect already-fetched local data.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

broker_view_app = typer.Typer(
    name="broker",
    help="Browse cached broker and foreign-flow data.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

broker_view_app.command("status")(broker_status)
broker_view_app.command("flow")(broker_flow)
broker_view_app.command("top")(broker_top)
broker_view_app.command("mappings")(broker_mappings)

view_app.add_typer(broker_view_app, name="broker")
