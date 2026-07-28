"""
CLI: live trade structure design (ADR-054).

  saham plan swing TICKER

Product job: horizon / stop / target / lots for a name already judged on
`saham screen accum TICKER`. Not a second screener. Not learning corpus
(`research`). Not paper notebook (`trade`) — use `trade accum log --from-plan`.

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.plan_swing_commands import swing as _swing_fn

plan_app = typer.Typer(
    name="plan",
    help=(
        "Trade structure for a chosen candidate (ADR-054). "
        "`plan swing` designs horizon / SL / TP / lots and writes a "
        "`swing_trade_plan` artifact; Action defaults to screen judgment "
        "(recompute only with `--with-market-context` / `--with-technical-gate`). "
        "Judge first: `saham screen accum TICKER`. "
        "Paper: `saham trade accum log --from-plan`. "
        "Lenses: `saham inspect risk|regime|signal accum|sentiment`. "
        "Frozen pre-open: `saham assess pre-open` (not this command)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

plan_app.command("swing")(_swing_fn)
