"""CLI: pre-open paper journal log, review, and outcome.

Layer: Adapter
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_pre_open_actions import (
    run_pre_open_paper_outcome,
    run_pre_open_paper_review,
)
from src.application.dto.analyze_pre_open import AnalyzePreOpenError
from src.application.use_case.analyze_pre_open_use_case import AnalyzePreOpenUseCase
from src.application.use_case.log_pre_open_trade_use_case import (
    LogPreOpenTradeRequest,
    LogPreOpenTradeUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config
from src.infrastructure.persistence.pre_open_paper_journal_csv import (
    PreOpenPaperJournalCsvStore,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.trade_journal_jsonl_writer import (
    TradeJournalJsonlWriter,
)


def pre_open_paper_log(
    observation_id: Annotated[
        str,
        typer.Option(
            "--observation-id",
            help="Learning observation id (from `saham analyze pre-open`)",
        ),
    ],
    opening_snapshot_id: Annotated[
        str,
        typer.Option(
            "--opening-snapshot-id",
            help="Opening track snapshot id (from `saham analyze pre-open`)",
        ),
    ],
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Pre-open paper CSV journal"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Log post-open assess rows to the pre-open paper notebook.

    Binds immutable observation_id + opening_snapshot_id from analyze pre-open.
    Dual-writes CSV journal and trades.jsonl. Idempotent.

    Example:
        saham trade pre-open log \\
          --observation-id OBS --opening-snapshot-id SNAP
    """
    cfg = load_app_config()
    journal_path = journal or Path(cfg.storage.pre_open_paper_journal)
    resolved_db = db_path or Path(cfg.storage.db_path)

    repository = SQLiteLearningArtifactRepository(resolved_db)
    analyze = AnalyzePreOpenUseCase(
        observations=repository,
        tracks=repository,
        pre_open_config=load_pre_open_screen_config(),
        clock_date=datetime.now(IDX_TIMEZONE).date(),
    )
    csv_store = PreOpenPaperJournalCsvStore(journal_path)
    jsonl_store = TradeJournalJsonlWriter(journal_path.parent / "trades.jsonl")
    use_case = LogPreOpenTradeUseCase(
        analyze=analyze,
        confirmation_store=csv_store,
        trade_journal_store=jsonl_store,
    )
    try:
        response = use_case.execute(
            LogPreOpenTradeRequest(
                observation_id=observation_id,
                opening_snapshot_id=opening_snapshot_id,
                journal_path=journal_path,
            )
        )
    except (AnalyzePreOpenError, ValueError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if response.duplicate:
        typer.echo(
            f"Already logged for {response.confirmed_at} — "
            f"no new rows added ({response.journal_path})"
        )
    else:
        typer.echo(
            f"Logged {response.logged_count} pre-open confirmation(s) "
            f"for {response.confirmed_at} → {response.journal_path}"
        )


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
