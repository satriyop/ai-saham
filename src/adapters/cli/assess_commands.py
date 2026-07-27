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
        "Frozen-plan confirmation only (identity-bound). "
        "Today: `assess pre-open` after `research pre-open capture` + `track`. "
        "Stdout only — not a research corpus write. "
        "Paper: `saham trade pre-open log`. "
        "Swing is not assessed here — re-run `saham plan swing`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

assess_app.command("pre-open")(_pre_open_fn)
