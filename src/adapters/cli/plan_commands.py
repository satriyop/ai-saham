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
        "`plan swing` is structure-only: capital / SL / TP / lots + "
        "`swing_trade_plan`. Action always inherits screen judgment "
        "(no analysis evidence flags; no Action recompute). "
        "Judgment + evidence: `saham screen accum TICKER` "
        "(`--full` / flow / sentiment / setup). "
        "Paper: `saham trade accum log --from-plan`. "
        "Regime lens only: `saham inspect regime` (display; not plan recompute). "
        "Frozen pre-open: `saham assess pre-open` (not this command)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

plan_app.command("swing")(_swing_fn)
