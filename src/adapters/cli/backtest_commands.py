"""
CLI: offline historical performance simulation.

  saham backtest screen accum
  saham backtest portfolio swing

Not live TradeSetup (`plan`). Not learning corpus (`research`).
Not integrity audit (`audit data`). Not paper notebook (`trade`).

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.backtest_portfolio_commands import portfolio_app
from src.adapters.cli.backtest_screen_commands import screen_app

backtest_app = typer.Typer(
    name="backtest",
    help=(
        "Offline historical performance simulation only.\n\n"
        "`screen accum` — discovery-filter replay + forward/exit stats "
        "(no capital book).\n"
        "`portfolio swing` — constrained multi-position swing-setup sim "
        "(capital, risk, slots, costs, equity).\n\n"
        "Live decision: `saham plan swing`. "
        "Corpus: `saham research`. "
        "Policy lifecycle (after portfolio sim): `saham policy accum tune|…|apply`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

backtest_app.add_typer(screen_app, name="screen")
backtest_app.add_typer(portfolio_app, name="portfolio")
