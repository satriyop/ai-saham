"""
CLI: contextual SignalEngine inspection under inspect.

  saham inspect signal accum TICKER

`signal` is a group of purpose-specific inspectors. Today only accumulation-flow
is mounted. Pre-open and swing signal inspect are not this command.

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.inspect_signal_accum_commands import accum as _accum_fn

signal_app = typer.Typer(
    name="signal",
    help=(
        "SignalEngine inspection by purpose/contract. "
        "Currently: `accum` = accumulation-flow only (not pre-open, not plan swing). "
        "No ENTER/WATCH/AVOID; no learning writes."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

signal_app.command("accum")(_accum_fn)
