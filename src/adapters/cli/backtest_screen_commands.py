"""
CLI: offline discovery-filter replay under backtest.

  saham backtest screen accum

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.backtest_screen_accum_commands import screen_accum as _accum_fn

screen_app = typer.Typer(
    name="screen",
    help=(
        "Historical replay of live screen filter packs (not corpus). "
        "`accum` = accumulation discovery filters + forward/exit stats. "
        "Live discover: `saham screen accum`. Portfolio book: `saham backtest portfolio swing`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

screen_app.command("accum")(_accum_fn)
