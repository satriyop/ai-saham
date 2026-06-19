"""
Lifecycle-oriented candidate discovery commands.

Layer: Adapter
"""

import typer

from src.adapters.cli.accumulation_commands import accumulation_run
from src.adapters.cli.screen_pre_open_commands import pre_open

screen_app = typer.Typer(
    name="screen",
    help="Candidate discovery — pre-open movers and accumulation screens.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

screen_app.command("pre-open")(pre_open)
screen_app.command("accum")(accumulation_run)
