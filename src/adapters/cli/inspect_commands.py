"""
CLI: live capability / evidence lenses (no final TradeSetup action).

  saham inspect risk|sentiment|regime|signal …

Not `plan` (TradeSetup). Not `assess` (frozen confirm). Not `research` (corpus).
Terminal charts retired — use `indicator compute|snapshot` for values; TUI later for charts.

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.inspect_regime_commands import regime as _regime_fn
from src.adapters.cli.inspect_risk_commands import risk as _risk_fn
from src.adapters.cli.inspect_sentiment_commands import sentiment as _sentiment_fn
from src.adapters.cli.inspect_signal_commands import signal_app

inspect_app = typer.Typer(
    name="inspect",
    help=(
        "Live single-subject capability/evidence lenses. "
        "No ENTER/WATCH/AVOID authority. "
        "Judgment: `saham screen accum TICKER`. "
        "Structure: `saham plan swing`. "
        "Frozen: `saham assess pre-open`. "
        "Browse raw stored series: `saham view`. "
        "Signal: `inspect signal accum` (accumulation-flow only)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

inspect_app.add_typer(signal_app, name="signal")
inspect_app.command("risk")(_risk_fn)
inspect_app.command("sentiment")(_sentiment_fn)
inspect_app.command("regime")(_regime_fn)
