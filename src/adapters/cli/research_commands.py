"""
CLI: research lifecycle — corpus construction and offline evaluation.

Commands:
  saham research signal …           — capture/backfill, labels, replay, readiness
  saham research accumulation …     — offline accumulation evaluation

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.analyze_accum_commands import accumulation_audit
from src.adapters.cli.analyze_signal_backfill_commands import signal_backfill_observations
from src.adapters.cli.analyze_signal_capture_commands import signal_capture_observations
from src.adapters.cli.analyze_signal_label_commands import signal_labels
from src.adapters.cli.analyze_signal_readiness_commands import signal_readiness
from src.adapters.cli.analyze_signal_replay_commands import signal_replay

research_app = typer.Typer(
    name="research",
    help=(
        "Research corpus and offline study — may persist observations/labels. "
        "CSV export only when explicitly requested."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_signal_app = typer.Typer(
    name="signal",
    help=(
        "SignalEngine research corpus: capture/backfill/label observations; "
        "replay and readiness reports (read-only)."
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
research_accumulation_app.command("evaluate")(accumulation_audit)

research_app.add_typer(research_signal_app, name="signal")
research_app.add_typer(research_accumulation_app, name="accumulation")
