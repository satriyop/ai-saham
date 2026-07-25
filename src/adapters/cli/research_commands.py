"""
CLI: research lifecycle — corpus construction, offline evaluation, session ritual.

Commands:
  saham research signal …           — multi-day signal corpus (capture/labels/…)
  saham research pre-open …         — pre-open scenario (capture/labels + same-day track/grade)
  saham research accumulation …     — offline accumulation evaluation

Pre-open subcommands (verb + scenario; no top-level learn/opening noun):
  capture | labels     — corpus (save decisions / outcomes)
  track | grade        — same-day ritual after capture
  prompt | tune        — non-authoritative post-session helpers

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.analyze_accum_commands import accumulation_audit
from src.adapters.cli.research_pre_open_grade_commands import grade
from src.adapters.cli.research_pre_open_prompt_commands import prompt
from src.adapters.cli.research_pre_open_track_commands import track
from src.adapters.cli.research_pre_open_tune_commands import tune
from src.adapters.cli.research_pre_open_capture_commands import pre_open_capture
from src.adapters.cli.research_pre_open_labels_commands import pre_open_labels
from src.adapters.cli.research_signal_backfill_commands import signal_backfill_observations
from src.adapters.cli.research_signal_capture_commands import signal_capture_observations
from src.adapters.cli.research_signal_label_commands import signal_labels
from src.adapters.cli.research_signal_readiness_commands import signal_readiness
from src.adapters.cli.research_signal_replay_commands import signal_replay

research_app = typer.Typer(
    name="research",
    help=(
        "Research: corpus construction and offline study. "
        "capture = save decisions; labels = outcomes. "
        "Pre-open also hosts same-day track/grade after capture. "
        "Live screens do not write (use screen for display only)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_signal_app = typer.Typer(
    name="signal",
    help=(
        "SignalEngine research corpus: capture/backfill/label observations; "
        "replay and readiness reports (read-only). Multi-day horizons only — "
        "not pre-open open_30m (use research pre-open labels)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_pre_open_app = typer.Typer(
    name="pre-open",
    help=(
        "Pre-open scenario under research. "
        "Corpus: capture (decisions), labels (open_30m outcomes). "
        "Same-day: track, grade, prompt, tune. "
        "Live display only: screen pre-open (no observation write)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_accumulation_app = typer.Typer(
    name="accumulation",
    help=(
        "Offline accumulation evaluation (DESCRIPTIVE). "
        "No database writes; CSV only with --output."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_signal_app.command("backfill")(signal_backfill_observations)
research_signal_app.command("capture")(signal_capture_observations)
research_signal_app.command("labels")(signal_labels)
research_signal_app.command("replay")(signal_replay)
research_signal_app.command("readiness")(signal_readiness)

research_pre_open_app.command("capture")(pre_open_capture)
research_pre_open_app.command("labels")(pre_open_labels)
research_pre_open_app.command("track")(track)
research_pre_open_app.command("grade")(grade)
research_pre_open_app.command("prompt")(prompt)
research_pre_open_app.command("tune")(tune)

research_accumulation_app.command("evaluate")(accumulation_audit)

research_app.add_typer(research_signal_app, name="signal")
research_app.add_typer(research_pre_open_app, name="pre-open")
research_app.add_typer(research_accumulation_app, name="accumulation")
