"""
CLI commands for paper trading notebooks only.

Commands (all under `saham trade`):
  saham trade pre-open log|outcome|review
  saham trade accum log|review

Not here:
  corpus / labels     → saham research pre-open|accum …
  config proposals    → saham policy accum …
  live assess / size  → saham analyze pre-open | analyze swing --capital

Layer: Adapter (routing only).
"""

from __future__ import annotations

import typer

from src.adapters.cli.trade_accum_commands import accumulation_log, accumulation_review
from src.adapters.cli.trade_pre_open_commands import (
    pre_open_paper_log,
    pre_open_paper_outcome,
    pre_open_paper_review,
)

trade_app = typer.Typer(
    name="trade",
    help=(
        "Paper trading notebook only (pre-open, accum). "
        "Corpus: `saham research`. Policy apply: `saham policy accum`. "
        "Sizing: `saham analyze swing --capital`. "
        "Post-open assess: `saham analyze pre-open`."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

trade_pre_open_app = typer.Typer(
    name="pre-open",
    help="Pre-open paper notebook: log assess rows, record fills, review buckets.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
trade_pre_open_app.command("log")(pre_open_paper_log)
trade_pre_open_app.command("outcome")(pre_open_paper_outcome)
trade_pre_open_app.command("review")(pre_open_paper_review)

trade_accum_app = typer.Typer(
    name="accum",
    help="Accum paper notebook: log candidates and review forward returns.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
trade_accum_app.command("log")(accumulation_log)
trade_accum_app.command("review")(accumulation_review)

trade_app.add_typer(trade_pre_open_app, name="pre-open")
trade_app.add_typer(trade_accum_app, name="accum")
