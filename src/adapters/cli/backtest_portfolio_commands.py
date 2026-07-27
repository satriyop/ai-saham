"""
CLI: offline portfolio simulators under backtest.

  saham backtest portfolio swing

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.backtest_portfolio_swing_commands import swing_backtest as _swing_fn

portfolio_app = typer.Typer(
    name="portfolio",
    help=(
        "Constrained multi-position historical simulation by product line. "
        "`swing` = swing-setup portfolio walk-forward (capital, risk, slots, costs). "
        "Live decision: `saham plan swing`. Policy apply: `saham policy accum apply`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

portfolio_app.command("swing")(_swing_fn)
