"""
CLI: live read-only signal inspection under analyze.

  saham analyze signal inspect TICKER

Corpus workflows live under `saham research signal …`.

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.analyze_signal_inspect_commands import signal_inspect

analyze_signal_app = typer.Typer(
    name="signal",
    help="Read-only live SignalEngine assessment from local data.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

analyze_signal_app.command("inspect")(signal_inspect)
