"""
CLI commands for technical indicator operations.

Commands (all under `saham indicator`):
  saham indicator compute INDICATOR TICKER  — compute any indicator
  saham indicator snapshot TICKER           — multi-indicator view (SMA + EMA + RSI)
  saham indicator create INTENT             — create custom formula via AI
  saham indicator list                      — list all available indicators
  saham indicator show NAME                 — show saved formula details
  saham indicator delete NAME               — remove saved formula

Layer: Adapter (router only)
"""

import typer

from src.adapters.cli.indicator_compute_commands import compute
from src.adapters.cli.indicator_formula_commands import (
    create,
    delete,
    list_indicators,
    show,
)
from src.adapters.cli.indicator_snapshot_commands import snapshot

indicator_app = typer.Typer(
    name="indicator",
    help="Technical indicators — compute, snapshot, manage custom formulas.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

indicator_app.command()(compute)
indicator_app.command()(snapshot)
indicator_app.command()(create)
indicator_app.command(name="list")(list_indicators)
indicator_app.command()(show)
indicator_app.command()(delete)
