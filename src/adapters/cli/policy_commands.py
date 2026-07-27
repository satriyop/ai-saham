"""
CLI: guarded setup-config policy lifecycle (not paper, not research corpus).

Commands (all under `saham policy`):
  saham policy accum backtest|tune|review|validate|apply|status

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.policy_accum_backtest_commands import swing_backtest
from src.adapters.cli.policy_accum_lifecycle_commands import (
    swing_apply,
    swing_review,
    swing_status,
    swing_tune,
    swing_validate,
)

policy_app = typer.Typer(
    name="policy",
    help=(
        "Guarded accum/swing setup config lifecycle "
        "(backtest → propose → OOS validate → YAML apply). "
        "Not paper trading (`saham trade`). "
        "Not research corpus (`saham research`)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

policy_accum_app = typer.Typer(
    name="accum",
    help=(
        "Accum/foreign-bounce setup policy: walk-forward backtest and "
        "database-owned proposal lifecycle with explicit YAML apply."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

policy_accum_app.command("backtest")(swing_backtest)
policy_accum_app.command("tune")(swing_tune)
policy_accum_app.command("review")(swing_review)
policy_accum_app.command("validate")(swing_validate)
policy_accum_app.command("apply")(swing_apply)
policy_accum_app.command("status")(swing_status)

policy_app.add_typer(policy_accum_app, name="accum")
