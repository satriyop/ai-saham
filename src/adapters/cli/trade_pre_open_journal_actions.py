"""Adapter helpers for pre-open paper journal review/outcome commands."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import typer

from src.adapters.cli.trade_pre_open_display import display_pre_open_paper_review
from src.application.services.pre_open_paper_journal import (
    PreOpenPaperJournalService,
)
from src.application.use_case.record_pre_open_paper_outcome_use_case import (
    RecordPreOpenPaperOutcomeRequest,
    RecordPreOpenPaperOutcomeUseCase,
)
from src.infrastructure.persistence.pre_open_paper_journal_csv import (
    PreOpenPaperJournalCsvStore,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)


def run_pre_open_paper_review(journal_path: Path, db_path: Path) -> None:
    if not journal_path.exists():
        typer.echo(
            f"No confirmation journal at '{journal_path}'.\n"
            "Run `saham trade log --type pre-open` after analyze first.", err=True,
        )
        raise typer.Exit(1)
    store = PreOpenPaperJournalCsvStore(journal_path)
    repository = SQLiteMarketRepository(db_path=db_path)
    report = PreOpenPaperJournalService(store=store, repository=repository).review()
    display_pre_open_paper_review(report, journal_path)


def run_pre_open_paper_outcome(
    *,
    ticker: str,
    entry: float,
    exit_price: float,
    result: str,
    confirmed_date: str | None,
    notes: str | None,
    journal_path: Path,
    db_path: Path,
) -> None:
    valid = {"target", "stop", "manual", "breakeven"}
    outcome_result = result.lower()
    if outcome_result not in valid:
        typer.echo(
            f"Error: --result must be one of: {', '.join(sorted(valid))}", err=True,
        )
        raise typer.Exit(1)
    if not journal_path.exists():
        typer.echo(
            f"No confirmation journal at '{journal_path}'.\n"
            "Run `saham trade log --type pre-open` first.", err=True,
        )
        raise typer.Exit(1)
    try:
        target_date = (
            date.fromisoformat(confirmed_date) if confirmed_date else date.today()
        )
    except ValueError:
        typer.echo("Error: --date must use YYYY-MM-DD format.", err=True)
        raise typer.Exit(1)
    service = PreOpenPaperJournalService(
        store=PreOpenPaperJournalCsvStore(journal_path),
        repository=SQLiteMarketRepository(db_path=db_path),
    )
    response = RecordPreOpenPaperOutcomeUseCase(journal_service=service).execute(
        RecordPreOpenPaperOutcomeRequest(
            confirmed_at=target_date, ticker=ticker.upper(),
            actual_entry_price=Decimal(str(entry)),
            actual_exit_price=Decimal(str(exit_price)),
            outcome_result=outcome_result, notes=notes,
        )
    )
    if not response.updated:
        typer.echo(
            f"No logged confirmation for {ticker.upper()} on {target_date}.", err=True,
        )
        raise typer.Exit(1)
    r_label = (
        f"{response.outcome_r:+.2f}R" if response.outcome_r is not None else "N/A"
    )
    typer.echo(
        f"Recorded outcome for {ticker.upper()} on {target_date}: "
        f"{outcome_result} | entry={entry:,.0f} "
        f"exit={exit_price:,.0f} | R={r_label}"
    )
