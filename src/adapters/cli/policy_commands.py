"""
CLI: guarded setup-config policy lifecycle (not paper, not research corpus).

Commands (all under `saham policy`):
  saham policy accum tune|review|validate|apply|status

Portfolio simulation: `saham backtest portfolio swing` (not under policy).

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

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
        "Guarded setup-config lifecycle for accum/swing setup policy "
        "(tune → review → validate → apply → status). "
        "Run portfolio simulation first: `saham backtest portfolio swing`. "
        "Not paper trading (`saham trade`). Not research corpus (`saham research`). "
        "Not live TradeSetup (`saham plan swing`)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

policy_accum_app = typer.Typer(
    name="accum",
    help=(
        "Accum/foreign-bounce setup policy lifecycle (database-owned proposals, "
        "explicit YAML apply). "
        "Simulation: `saham backtest portfolio swing` (not this group)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

policy_accum_app.command("tune")(swing_tune)
policy_accum_app.command("review")(swing_review)
policy_accum_app.command("validate")(swing_validate)
policy_accum_app.command("apply")(swing_apply)
policy_accum_app.command("status")(swing_status)

policy_app.add_typer(policy_accum_app, name="accum")
