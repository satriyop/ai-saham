"""
CLI: research lifecycle — corpus construction and offline cohort study only.

Commands:
  saham research pre-open …   — pre-open learning corpus
  saham research accum …      — accumulation learning corpus

Not paper trading (`saham trade`). Not policy YAML apply (`saham policy`).

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.research_accum_backfill_commands import signal_backfill_observations
from src.adapters.cli.research_accum_capture_commands import signal_capture_observations
from src.adapters.cli.research_accum_evaluate_commands import (
    accumulation_evaluate,
    accumulation_labels,
    accumulation_replay,
    accumulation_status,
)
from src.adapters.cli.research_pre_open_capture_commands import pre_open_capture
from src.adapters.cli.research_pre_open_evaluate_commands import (
    pre_open_evaluate,
    pre_open_status,
)
from src.adapters.cli.research_pre_open_labels_commands import pre_open_labels
from src.adapters.cli.research_pre_open_track_commands import track

research_app = typer.Typer(
    name="research",
    help=(
        "Research corpus / ML feeder only. "
        "capture = save decisions; labels = outcomes; evaluate = cohort study. "
        "Live without write: `saham screen`. Paper: `saham trade`. "
        "Policy apply: `saham policy accum`. Not live TradeSetup (`plan`)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_pre_open_app = typer.Typer(
    name="pre-open",
    help=(
        "Pre-open corpus: capture decisions, track opening samples, "
        "label open_30m outcomes, evaluate cohorts, inspect status. "
        "Live display only: screen pre-open (no observation write)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

research_accum_app = typer.Typer(
    name="accum",
    help=(
        "Accum corpus: capture, backfill, labels, compatible-cohort "
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

research_accum_app.command("capture")(signal_capture_observations)
research_accum_app.command("backfill")(signal_backfill_observations)
research_accum_app.command("labels")(accumulation_labels)
research_accum_app.command("evaluate")(accumulation_evaluate)
research_accum_app.command("replay")(accumulation_replay)
research_accum_app.command("status")(accumulation_status)

research_app.add_typer(research_pre_open_app, name="pre-open")
research_app.add_typer(research_accum_app, name="accum")
