"""
CLI commands for active trading workflows.

Commands (all under `saham trade`):
  saham trade swing …     — swing trading workflow (sub-group)
  saham trade intraday …  — intraday screening and journaling (sub-group)

Layer: Adapter
"""

import typer

from src.adapters.cli.swing_commands import swing_app
from src.adapters.cli.screen_commands import intraday_app

trade_app = typer.Typer(
    name="trade",
    help="Active trading workflows — swing and intraday.",
    no_args_is_help=True,
)

trade_app.add_typer(swing_app, name="swing")
trade_app.add_typer(intraday_app, name="intraday")
