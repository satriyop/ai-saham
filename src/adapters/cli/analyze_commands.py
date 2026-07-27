"""
CLI commands for analysis and insights (transitional until ADR-050 Slice 3).

Remaining under `saham analyze` until inspect migration (ADR-050 Slice 3):
  saham analyze risk|sentiment|audit|regime|signal|chart

Retired: analyze swing → plan swing; analyze pre-open → assess pre-open;
analyze compare / swing-compare removed.

Layer: Adapter
"""

import typer

from src.adapters.cli.analyze_chart_commands import chart_app
from src.adapters.cli.analyze_regime_commands import regime as _regime_fn
from src.adapters.cli.analyze_risk_commands import risk as _risk_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment as _sentiment_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment_audit as _sentiment_audit_fn
from src.adapters.cli.analyze_signal_router import analyze_signal_app

analyze_app = typer.Typer(
    name="analyze",
    help=(
        "Live analysis lenses and lenses only (transitional). "
        "Live TradeSetup: `saham plan swing`. "
        "Corpus: `saham research`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

analyze_app.add_typer(chart_app, name="chart")
analyze_app.add_typer(analyze_signal_app, name="signal")

analyze_app.command("risk")(_risk_fn)
analyze_app.command("sentiment")(_sentiment_fn)
analyze_app.command("audit")(_sentiment_audit_fn)
analyze_app.command("regime")(_regime_fn)
