"""
CLI: live capability / evidence lenses (no final TradeSetup action).

  saham inspect risk|sentiment|regime|signal|chart …

Not `plan` (TradeSetup). Not `assess` (frozen confirm). Not `research` (corpus).

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.inspect_chart_commands import chart_app
from src.adapters.cli.inspect_regime_commands import regime as _regime_fn
from src.adapters.cli.inspect_risk_commands import risk as _risk_fn
from src.adapters.cli.inspect_sentiment_commands import sentiment as _sentiment_fn
from src.adapters.cli.inspect_signal_commands import signal_app

inspect_app = typer.Typer(
    name="inspect",
    help=(
        "Live single-subject capability/evidence lenses. "
        "No ENTER/WATCH/AVOID authority. "
        "Trade plan: `saham plan swing`. Frozen confirm: `saham assess pre-open`. "
        "Signal inspect is purpose-specific: `inspect signal accum` (accum-flow only)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

inspect_app.add_typer(chart_app, name="chart")
inspect_app.add_typer(signal_app, name="signal")
inspect_app.command("risk")(_risk_fn)
inspect_app.command("sentiment")(_sentiment_fn)
inspect_app.command("regime")(_regime_fn)
