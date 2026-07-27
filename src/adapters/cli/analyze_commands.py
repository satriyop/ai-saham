"""
CLI commands for analysis and insights.

Commands (all under `saham analyze`):
  saham analyze risk TICKER       — rule-based risk assessment
  saham analyze compare TICKER…   — side-by-side multi-ticker comparison
  saham analyze sentiment TICKER  — news sentiment analysis
  saham analyze audit             — audit past sentiment accuracy
  saham analyze regime            — IHSG market regime context
  saham analyze swing             — swing analysis
  saham analyze swing-compare     — swing comparison
  saham analyze signal inspect    — live read-only SignalEngine inspect
  saham analyze chart             — terminal ASCII charts (sub-group)

Corpus backfill/labels/replay/readiness and accumulation evaluate live under
`saham research …`.

Layer: Adapter
"""

import typer

from src.adapters.cli.analyze_chart_commands import chart_app
from src.adapters.cli.analyze_compare_commands import compare as _compare_fn
from src.adapters.cli.analyze_pre_open_commands import pre_open as _pre_open_fn
from src.adapters.cli.analyze_regime_commands import regime as _regime_fn
from src.adapters.cli.analyze_risk_commands import risk as _risk_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment as _sentiment_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment_audit as _sentiment_audit_fn
from src.adapters.cli.analyze_signal_router import analyze_signal_app
from src.adapters.cli.analyze_swing_commands import swing as _swing_fn
from src.adapters.cli.analyze_swing_compare_commands import swing_compare as _swing_compare_fn

analyze_app = typer.Typer(
    name="analyze",
    help=(
        "Live analysis and insights — risk, sentiment, regime, swing, "
        "pre-open (post-open assess of NCP plan), signal inspect, charts. "
        "Corpus workflows: `saham research`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

analyze_app.add_typer(chart_app, name="chart")
analyze_app.add_typer(analyze_signal_app, name="signal")

analyze_app.command("risk")(_risk_fn)
analyze_app.command("compare")(_compare_fn)
analyze_app.command("sentiment")(_sentiment_fn)
analyze_app.command("audit")(_sentiment_audit_fn)
analyze_app.command("regime")(_regime_fn)
analyze_app.command("swing")(_swing_fn)
analyze_app.command("swing-compare")(_swing_compare_fn)
analyze_app.command("pre-open")(_pre_open_fn)
