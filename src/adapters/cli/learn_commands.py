"""
CLI commands for the opening session learning loop.

Commands (all under `saham learn`):
  snapshot  — 08:57 WIB: NCP-locked pre-open screener capture
  track     — 09:00–09:30 WIB: 5-min orderbook loop for all screened tickers
  grade     — 09:35+ WIB: deterministic accuracy report (no network)
  labels    — open_30m outcome labels from freezes + tracks
  tune      — 09:40+ WIB: DeepSeek AI config recommendations
  prompt    — on-demand: copy-paste AI prompt for any AI assistant

All commands accept --date YYYY-MM-DD for retrospective runs
and --force to bypass IDX trading-hour guards.

Layer: Adapter
"""

import typer

from src.adapters.cli.learn_grade_commands import grade
from src.adapters.cli.learn_labels_commands import labels
from src.adapters.cli.learn_prompt_commands import prompt
from src.adapters.cli.learn_snapshot_commands import snapshot
from src.adapters.cli.learn_track_commands import track
from src.adapters.cli.learn_tune_commands import tune

learn_app = typer.Typer(
    name="learn",
    help="Learning loop — snapshot, track, grade, labels, prompt, and tune opening sessions.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

learn_app.command("snapshot")(snapshot)
learn_app.command("track")(track)
learn_app.command("grade")(grade)
learn_app.command("labels")(labels)
learn_app.command("tune")(tune)
learn_app.command("prompt")(prompt)
