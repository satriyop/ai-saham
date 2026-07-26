"""
CLI commands for active trading workflows.

Commands (all under `saham trade`):
  saham trade confirm             — opening confirmation gate
  saham trade log --type swing    — log swing accumulation candidate
  saham trade log --type intraday — log intraday confirmation decisions
  saham trade review intraday     — review intraday confirmation journal
  saham trade review swing        — review swing accumulation journal
  saham trade outcome             — record intraday outcome
  saham trade size                — ATR-based swing position sizing
  saham trade swing ...           — database-owned swing policy learning
  saham trade backtest-intraday   — intraday workflow daily-OHLC proxy simulation
  saham trade migrate-journal     — one-time migration of CSV journals to trades.jsonl

Layer: Adapter
"""

import typer

from src.adapters.cli.trade_accum_commands import accumulation_review
from src.adapters.cli.trade_intraday_commands import (
    confirm_open,
    confirm_outcome,
    confirm_review,
    intraday_backtest,
)
from src.adapters.cli.trade_journal_migration_commands import trade_migrate_journal
from src.adapters.cli.trade_log_router_commands import trade_log
from src.adapters.cli.trade_swing_commands import size, swing_backtest
from src.adapters.cli.trade_swing_learning_commands import (
    swing_apply,
    swing_review,
    swing_status,
    swing_tune,
    swing_validate,
)

trade_app = typer.Typer(
    name="trade",
    help="Paper trading workspace — confirmation, journals, sizing, and workflow backtests.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

trade_review_app = typer.Typer(
    name="review",
    help="Review paper-trade journals by workflow.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
trade_review_app.command("intraday")(confirm_review)
trade_review_app.command("swing")(accumulation_review)

trade_swing_app = typer.Typer(
    name="swing",
    help="Swing backtest and database-owned policy review lifecycle.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
trade_swing_app.command("backtest")(swing_backtest)
trade_swing_app.command("tune")(swing_tune)
trade_swing_app.command("review")(swing_review)
trade_swing_app.command("validate")(swing_validate)
trade_swing_app.command("apply")(swing_apply)
trade_swing_app.command("status")(swing_status)

trade_app.command("confirm")(confirm_open)
trade_app.add_typer(trade_review_app, name="review")
trade_app.command("outcome")(confirm_outcome)
trade_app.command("size")(size)
trade_app.add_typer(trade_swing_app, name="swing")
trade_app.command("backtest-intraday")(intraday_backtest)
trade_app.command("log")(trade_log)
trade_app.command("migrate-journal")(trade_migrate_journal)
