"""
CLI: research lifecycle — corpus construction, offline evaluation, session ritual.

Commands:
  saham research accumulation …     — accumulation learning lifecycle
  saham research pre-open …         — pre-open learning lifecycle

Pre-open subcommands (verb + scenario; no top-level learn/opening noun):
  capture | labels     — corpus (save decisions / outcomes)
  track                — database-owned opening-session samples
  evaluate | status    — compatible cohort evaluation and readiness

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.research_learning_commands import (
    accumulation_evaluate,
    accumulation_labels,
    accumulation_replay,
    accumulation_status,
    pre_open_evaluate,
    pre_open_status,
)
from src.adapters.cli.research_pre_open_capture_commands import pre_open_capture
from src.adapters.cli.research_pre_open_labels_commands import pre_open_labels
from src.adapters.cli.research_pre_open_track_commands import track
from src.adapters.cli.research_signal_backfill_commands import signal_backfill_observations
from src.adapters.cli.research_signal_capture_commands import signal_capture_observations

research_app = typer.Typer(
    name="research",
    help=(
        "Research: corpus construction and offline study. "
        "capture = save decisions; labels = outcomes. "
        "Pre-open also hosts database-owned opening tracks. "
        "Live screens do not write (use screen for display only)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_pre_open_app = typer.Typer(
    name="pre-open",
    help=(
        "Pre-open scenario under research. "
        "Capture decisions, track opening samples, label open_30m outcomes, "
        "evaluate compatible sessions, and inspect status. "
        "Live display only: screen pre-open (no observation write)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_accumulation_app = typer.Typer(
    name="accumulation",
    help=(
        "Database-owned accumulation capture, labels, compatible-cohort "
        "evaluation, replay inspection, and status."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_pre_open_app.command("capture")(pre_open_capture)
research_pre_open_app.command("labels")(pre_open_labels)
research_pre_open_app.command("track")(track)
research_pre_open_app.command("evaluate")(pre_open_evaluate)
research_pre_open_app.command("status")(pre_open_status)

research_accumulation_app.command("capture")(signal_capture_observations)
research_accumulation_app.command("backfill")(signal_backfill_observations)
research_accumulation_app.command("labels")(accumulation_labels)
research_accumulation_app.command("evaluate")(accumulation_evaluate)
research_accumulation_app.command("replay")(accumulation_replay)
research_accumulation_app.command("status")(accumulation_status)

research_app.add_typer(research_pre_open_app, name="pre-open")
research_app.add_typer(research_accumulation_app, name="accumulation")
