"""
CLI commands for analysis and insights (transitional until ADR-050 Slice 3).

Remaining under `saham analyze` until inspect/assess migration:
  saham analyze risk TICKER
  saham analyze sentiment TICKER
  saham analyze audit
  saham analyze regime
  saham analyze signal inspect
  saham analyze chart …
  saham analyze pre-open

Retired (ADR-050): analyze swing → plan swing; analyze compare / swing-compare removed.

Layer: Adapter
"""

import typer

from src.adapters.cli.analyze_chart_commands import chart_app
from src.adapters.cli.analyze_pre_open_commands import pre_open as _pre_open_fn
from src.adapters.cli.analyze_regime_commands import regime as _regime_fn
from src.adapters.cli.analyze_risk_commands import risk as _risk_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment as _sentiment_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment_audit as _sentiment_audit_fn
from src.adapters.cli.analyze_signal_router import analyze_signal_app

analyze_app = typer.Typer(
    name="analyze",
    help=(
        "Live analysis lenses and pre-open assess (transitional). "
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
analyze_app.command("pre-open")(_pre_open_fn)
