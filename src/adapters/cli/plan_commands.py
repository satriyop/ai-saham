"""
CLI: live trade plan composition.

  saham plan swing TICKER

Authority: TradeSetup from SignalEngine + RiskEngine (ADR-032/050).
Not learning corpus (`research`). Not paper notebook (`trade`).

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.plan_swing_commands import swing as _swing_fn

plan_app = typer.Typer(
    name="plan",
    help=(
        "Live trade plan composition. "
        "`plan swing` produces authoritative TradeSetup (action + plan fields). "
        "Evidence lenses: `saham inspect risk|regime|signal accum|sentiment`. "
        "Paper: `saham trade accum log`. Not a research write (`research`). "
        "Frozen pre-open: `saham assess pre-open` (not this command)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

plan_app.command("swing")(_swing_fn)
