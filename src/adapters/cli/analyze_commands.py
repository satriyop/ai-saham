"""
CLI commands for analysis and insights.

Commands (all under `saham analyze`):
  saham analyze risk TICKER       — rule-based risk assessment
  saham analyze compare TICKER…   — side-by-side multi-ticker comparison
  saham analyze sentiment TICKER  — news sentiment analysis
  saham analyze audit             — audit past sentiment accuracy
  saham analyze regime            — IHSG market regime context
  saham analyze chart             — terminal ASCII charts (sub-group)

Layer: Adapter
"""

import typer

from src.adapters.cli.analyze_accum_commands import accumulation_audit as _accumulation_audit_fn
from src.adapters.cli.analyze_chart_commands import chart_app
from src.adapters.cli.analyze_compare_commands import compare as _compare_fn
from src.adapters.cli.analyze_regime_commands import regime as _regime_fn
from src.adapters.cli.analyze_risk_commands import risk as _risk_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment as _sentiment_fn
from src.adapters.cli.analyze_sentiment_commands import sentiment_audit as _sentiment_audit_fn
from src.adapters.cli.analyze_signal_commands import (
    signal_backfill_observations as _signal_backfill_observations_fn,
)
from src.adapters.cli.analyze_signal_commands import signal_labels as _signal_labels_fn
from src.adapters.cli.analyze_signal_commands import signal_readiness as _signal_readiness_fn
from src.adapters.cli.analyze_signal_commands import signal_replay as _signal_replay_fn
from src.adapters.cli.analyze_swing_commands import swing as _swing_fn
from src.adapters.cli.analyze_swing_compare_commands import swing_compare as _swing_compare_fn

analyze_app = typer.Typer(
    name="analyze",
    help="Analysis and insights — risk, sentiment, market regime, charts.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# Register chart as a nested sub-group
analyze_app.add_typer(chart_app, name="chart")

# Register commands from focused command modules (no logic duplication)
analyze_app.command("risk")(_risk_fn)
analyze_app.command("compare")(_compare_fn)
analyze_app.command("sentiment")(_sentiment_fn)
analyze_app.command("audit")(_sentiment_audit_fn)
analyze_app.command("regime")(_regime_fn)
analyze_app.command("swing")(_swing_fn)
analyze_app.command("accum-audit")(_accumulation_audit_fn)
analyze_app.command("swing-compare")(_swing_compare_fn)
analyze_app.command("signal-backfill-observations")(_signal_backfill_observations_fn)
analyze_app.command("signal-labels")(_signal_labels_fn)
analyze_app.command("signal-readiness")(_signal_readiness_fn)
analyze_app.command("signal-replay")(_signal_replay_fn)
