"""
CLI commands for active intraday trading workflows.
Compatibility-only re-export module.

Layer: Adapter
"""

from src.adapters.cli.trade_intraday_backtest_commands import intraday_backtest
from src.adapters.cli.trade_intraday_confirm_commands import (
    DEFAULT_CONFIRMATION_JOURNAL_PATH,
    DEFAULT_CONFIRMATION_PATH,
    _confirm_log_impl,
    confirm_log,
    confirm_open,
    confirm_outcome,
    confirm_review,
)

__all__ = [
    "DEFAULT_CONFIRMATION_JOURNAL_PATH",
    "DEFAULT_CONFIRMATION_PATH",
    "_confirm_log_impl",
    "confirm_open",
    "confirm_log",
    "confirm_review",
    "confirm_outcome",
    "intraday_backtest",
]
