"""
CLI commands for the opening session ops loop (same-day ritual only).

Family rule: screen = live; research * capture = save decisions;
research * labels = outcomes; learn = same-day ops only.

Commands (all under `saham learn`):
  track     — 09:00–09:30 WIB: 5-min orderbook loop for captured tickers
  grade     — 09:35+ WIB: deterministic session scorecard (no network)
  tune      — 09:40+ WIB: DeepSeek AI config recommendations
  prompt    — on-demand: copy-paste AI prompt for any AI assistant

Decision write is only: saham research pre-open capture
Corpus open_30m labels: saham research pre-open labels

All commands accept --date YYYY-MM-DD for retrospective runs
and --force to bypass IDX trading-hour guards.

Layer: Adapter
"""

import typer

from src.adapters.cli.learn_grade_commands import grade
from src.adapters.cli.learn_prompt_commands import prompt
from src.adapters.cli.learn_track_commands import track
from src.adapters.cli.learn_tune_commands import tune

learn_app = typer.Typer(
    name="learn",
    help=(
        "Opening-session ops — same-day ritual only (track, grade, prompt, tune). "
        "Not multi-day corpus. "
        "Save decisions: research pre-open capture; outcomes: research pre-open labels."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

learn_app.command("track")(track)
learn_app.command("grade")(grade)
learn_app.command("tune")(tune)
learn_app.command("prompt")(prompt)
