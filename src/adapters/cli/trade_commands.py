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
  saham trade backtest-swing      — swing workflow walk-forward backtest
  saham trade tune-swing          — swing tuning review from backtest attribution
  saham trade tuning-status       — read-only swing tuning loop status
  saham trade review-tuning-swing — review saved swing tuning runs
  saham trade validate-tuning-patch — validate exported swing tuning patch JSON
  saham trade apply-tuning-patch  — dry-run or explicitly apply exported tuning patch changes
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
from src.adapters.cli.trade_swing_commands import size, swing_backtest, swing_tune
from src.adapters.cli.trade_tuning_patch_commands import (
    apply_tuning_patch,
    validate_tuning_patch,
)
from src.adapters.cli.trade_tuning_status_commands import (
    review_tuning_swing,
    tuning_status,
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

trade_app.command("confirm")(confirm_open)
trade_app.add_typer(trade_review_app, name="review")
trade_app.command("outcome")(confirm_outcome)
trade_app.command("size")(size)
trade_app.command("backtest-swing")(swing_backtest)
trade_app.command("tune-swing")(swing_tune)
trade_app.command("backtest-intraday")(intraday_backtest)
trade_app.command("tuning-status")(tuning_status)
trade_app.command("review-tuning-swing")(review_tuning_swing)
trade_app.command("validate-tuning-patch")(validate_tuning_patch)
trade_app.command("apply-tuning-patch")(apply_tuning_patch)
trade_app.command("log")(trade_log)
trade_app.command("migrate-journal")(trade_migrate_journal)
