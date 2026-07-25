"""
CLI: research lifecycle — corpus construction and offline evaluation.

Commands:
  saham research signal …           — multi-day signal corpus (capture/labels/…)
  saham research pre-open …         — pre-open corpus (capture observations, open_30m labels)
  saham research accumulation …     — offline accumulation evaluation

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.analyze_accum_commands import accumulation_audit
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
        "Research corpus and offline study. "
        "capture = save decisions; labels = outcomes. "
        "Live screens do not write (use screen for display only). "
        "CSV export only when explicitly requested."
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
        "Pre-open session research corpus: capture saves observations to DB, then "
        "open_30m labels from saved decisions + learn track data. Live screen pre-open does not write."
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

research_accumulation_app.command("evaluate")(accumulation_audit)

research_app.add_typer(research_signal_app, name="signal")
research_app.add_typer(research_pre_open_app, name="pre-open")
research_app.add_typer(research_accumulation_app, name="accumulation")
