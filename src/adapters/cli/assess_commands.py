"""
CLI: frozen-plan confirmation.

  saham assess pre-open

Confirms an immutable learning observation against later reality.
Not live TradeSetup (`plan`). Not learning writes (`research`).

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.assess_pre_open_commands import pre_open as _pre_open_fn

assess_app = typer.Typer(
    name="assess",
    help=(
        "Frozen-plan confirmation only. "
        "`assess pre-open` reads observation + opening track; stdout only. "
        "Paper log: `saham trade pre-open log`. Live swing plan: `saham plan swing`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

assess_app.command("pre-open")(_pre_open_fn)
