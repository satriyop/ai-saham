"""CLI: pre-open paper journal review and outcome.

Layer: Adapter
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_pre_open_journal_actions import (
    run_pre_open_paper_outcome,
    run_pre_open_paper_review,
)
from src.infrastructure.config.app_config import load_app_config


def pre_open_paper_review(
    journal: Annotated[
        Optional[Path], typer.Option("--journal", help="Pre-open paper CSV journal")
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Review pre-open paper journal buckets."""
    cfg = load_app_config()
    run_pre_open_paper_review(
        journal_path=journal or Path(cfg.storage.pre_open_paper_journal),
        db_path=db_path or Path(cfg.storage.db_path),
    )


def pre_open_paper_outcome(
    ticker: Annotated[str, typer.Argument(help="Ticker to update")],
    entry: Annotated[float, typer.Option("--entry", help="Actual entry price", min=0.0001)],
    exit_price: Annotated[float, typer.Option("--exit", help="Actual exit price", min=0.0001)],
    result: Annotated[
        str, typer.Option("--result", help="Outcome: target/stop/manual/breakeven")
    ] = "manual",
    confirmed_date: Annotated[
        Optional[str], typer.Option("--date", help="Date YYYY-MM-DD")
    ] = None,
    notes: Annotated[
        Optional[str], typer.Option("--notes", help="Execution notes")
    ] = None,
    journal: Annotated[
        Optional[Path], typer.Option("--journal", help="Pre-open paper CSV journal")
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Record actual outcome on a pre-open paper journal row."""
    cfg = load_app_config()
    run_pre_open_paper_outcome(
        ticker=ticker,
        entry=entry,
        exit_price=exit_price,
        result=result,
        confirmed_date=confirmed_date,
        notes=notes,
        journal_path=journal or Path(cfg.storage.pre_open_paper_journal),
        db_path=db_path or Path(cfg.storage.db_path),
    )
