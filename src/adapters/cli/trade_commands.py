"""
CLI commands for active trading workflows.

Commands (all under `saham trade`):
  saham trade confirm             — opening confirmation gate
  saham trade log intraday        — log intraday confirmation decisions
  saham trade log swing           — log swing accumulation candidates
  saham trade review intraday     — review intraday confirmation journal
  saham trade review swing        — review swing accumulation journal
  saham trade outcome             — record intraday outcome
  saham trade size                — ATR-based swing position sizing
  saham trade backtest-swing      — swing workflow walk-forward backtest
  saham trade backtest-intraday   — intraday workflow walk-forward backtest

Layer: Adapter
"""

import typer

from src.adapters.cli.accumulation_commands import accumulation_log, accumulation_review
from src.adapters.cli.swing_commands import size, swing_backtest
from src.adapters.cli.trade_intraday_commands import (
    confirm_log,
    confirm_open,
    confirm_outcome,
    confirm_review,
    intraday_backtest,
)

trade_app = typer.Typer(
    name="trade",
    help="Paper trading workspace — confirmation, journals, sizing, and workflow backtests.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

trade_log_app = typer.Typer(
    name="log",
    help="Log paper-trade decisions by workflow.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
trade_log_app.command("intraday")(confirm_log)
trade_log_app.command("swing")(accumulation_log)

trade_review_app = typer.Typer(
    name="review",
    help="Review paper-trade journals by workflow.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
trade_review_app.command("intraday")(confirm_review)
trade_review_app.command("swing")(accumulation_review)

trade_app.command("confirm")(confirm_open)
trade_app.add_typer(trade_log_app, name="log")
trade_app.add_typer(trade_review_app, name="review")
trade_app.command("outcome")(confirm_outcome)
trade_app.command("size")(size)
trade_app.command("backtest-swing")(swing_backtest)
trade_app.command("backtest-intraday")(intraday_backtest)
