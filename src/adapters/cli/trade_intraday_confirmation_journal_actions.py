"""Adapter helpers for intraday confirmation journal commands."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import typer

from src.adapters.cli.trade_intraday_display import display_intraday_review
from src.application.services.intraday_confirmation_journal import (
    IntradayConfirmationJournalService,
)
from src.application.use_case.record_intraday_confirmation_outcome_use_case import (
    RecordIntradayConfirmationOutcomeRequest,
    RecordIntradayConfirmationOutcomeUseCase,
)
from src.infrastructure.persistence.intraday_confirmation_csv import (
    IntradayConfirmationCsvStore,
)
from src.infrastructure.persistence.sqlite_market_repository import (
    SQLiteMarketRepository,
)


def run_confirm_review(journal_path: Path, db_path: Path) -> None:
    if not journal_path.exists():
        typer.echo(
            f"No confirmation journal at '{journal_path}'.\n"
            "Run `saham trade log --type pre-open` after analyze first.", err=True,
        )
        raise typer.Exit(1)
    store = IntradayConfirmationCsvStore(journal_path)
    repository = SQLiteMarketRepository(db_path=db_path)
    report = IntradayConfirmationJournalService(store=store, repository=repository).review()
    display_intraday_review(report, journal_path)


def run_confirm_outcome(
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
    service = IntradayConfirmationJournalService(
        store=IntradayConfirmationCsvStore(journal_path),
        repository=SQLiteMarketRepository(db_path=db_path),
    )
    response = RecordIntradayConfirmationOutcomeUseCase(journal_service=service).execute(
        RecordIntradayConfirmationOutcomeRequest(
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
