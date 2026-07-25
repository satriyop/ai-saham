"""
CLI commands for the opening session learning loop (same-day ops only).

Commands (all under `saham learn`):
  snapshot  — 08:57 WIB: NCP-locked pre-open screener capture
  track     — 09:00–09:30 WIB: 5-min orderbook loop for all screened tickers
  grade     — 09:35+ WIB: deterministic accuracy report (no network)
  tune      — 09:40+ WIB: DeepSeek AI config recommendations
  prompt    — on-demand: copy-paste AI prompt for any AI assistant

Corpus open_30m labels live under: saham research pre-open labels
(not under learn — clean break, no aliases).

All commands accept --date YYYY-MM-DD for retrospective runs
and --force to bypass IDX trading-hour guards.

Layer: Adapter
"""

import typer

from src.adapters.cli.learn_grade_commands import grade
from src.adapters.cli.learn_prompt_commands import prompt
from src.adapters.cli.learn_snapshot_commands import snapshot
from src.adapters.cli.learn_track_commands import track
from src.adapters.cli.learn_tune_commands import tune

learn_app = typer.Typer(
    name="learn",
    help=(
        "Opening-session ops loop — snapshot, track, grade, prompt, and tune. "
        "For open_30m corpus labels use: saham research pre-open labels."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

learn_app.command("snapshot")(snapshot)
learn_app.command("track")(track)
learn_app.command("grade")(grade)
learn_app.command("tune")(tune)
learn_app.command("prompt")(prompt)
