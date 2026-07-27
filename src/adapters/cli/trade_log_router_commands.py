"""
CLI command for unified trade journal logging.

Layer: Adapter
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_accum_commands import (
    FOREIGN_BOUNCE_SETUP,
    run_accumulation_log_command,
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
from src.infrastructure.persistence.trade_journal_jsonl_writer import (
    TradeJournalJsonlWriter,
)


def trade_log(
    trade_type: Annotated[
        str,
        typer.Option("--type", help="Trade type: swing or pre-open"),
    ],
    # swing options
    ticker: Annotated[
        Optional[str],
        typer.Option("--ticker", "-t", help="Ticker to log (swing only)"),
    ] = None,
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation window in sessions (swing only)", min=3),
    ] = 7,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry-price", help="Entry price override (swing only)"),
    ] = None,
    from_analysis: Annotated[
        bool,
        typer.Option(
            "--from-analysis",
            help="Record setup match, failed gates, trade plan (swing only)",
        ),
    ] = False,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup name"),
    ] = FOREIGN_BOUNCE_SETUP,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Include market regime label (swing only)"),
    ] = False,
    regime_universe: Annotated[
        Optional[str],
        typer.Option("--regime-universe", help="Universe for regime breadth"),
    ] = "lq45",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "IHSG",
    # pre-open options (immutable IDs from analyze pre-open)
    observation_id: Annotated[
        Optional[str],
        typer.Option(
            "--observation-id",
            help="Learning observation id (required for --type pre-open)",
        ),
    ] = None,
    opening_snapshot_id: Annotated[
        Optional[str],
        typer.Option(
            "--opening-snapshot-id",
            help="Opening track snapshot id (required for --type pre-open)",
        ),
    ] = None,
    # shared
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Override journal file path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Log a paper-trade decision to the unified trade journal (trades.jsonl).

    Writes to the type-specific CSV journal and to journals/trades.jsonl.
    Idempotent: re-running for the same key never duplicates rows.

    Examples:
        saham trade log --type swing --ticker BBRI --window 7
        saham trade log --type swing --ticker BBCA --from-analysis --with-regime
        saham trade log --type pre-open \\
          --observation-id OBS --opening-snapshot-id SNAP
    """
    cfg = load_app_config()
    if trade_type == "swing":
        if ticker is None:
            typer.echo("--ticker is required for --type swing", err=True)
            raise typer.Exit(1)
        run_accumulation_log_command(
            ticker=ticker,
            window=window,
            entry_price=entry_price,
            from_analysis=from_analysis,
            setup=setup,
            with_regime=with_regime,
            regime_universe=regime_universe,
            benchmark=benchmark,
            journal_path=journal or Path(cfg.storage.accum_journal),
            db_path=db_path or Path(cfg.storage.db_path),
        )
    elif trade_type == "pre-open":
        _log_pre_open(
            observation_id=observation_id,
            opening_snapshot_id=opening_snapshot_id,
            journal=journal or Path(cfg.storage.pre_open_paper_journal),
            db_path=db_path or Path(cfg.storage.db_path),
        )
    elif trade_type == "intraday":
        typer.echo(
            "Unknown --type 'intraday'. Use --type pre-open with "
            "--observation-id and --opening-snapshot-id "
            "(from `saham analyze pre-open`).",
            err=True,
        )
        raise typer.Exit(1)
    else:
        typer.echo(
            f"Unknown --type '{trade_type}'. Valid values: swing, pre-open",
            err=True,
        )
        raise typer.Exit(1)


def _log_pre_open(
    *,
    observation_id: str | None,
    opening_snapshot_id: str | None,
    journal: Path,
    db_path: Path,
) -> None:
    if not observation_id or not opening_snapshot_id:
        typer.echo(
            "--observation-id and --opening-snapshot-id are required for "
            "--type pre-open (copy from `saham analyze pre-open`).",
            err=True,
        )
        raise typer.Exit(1)

    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        SQLiteLearningArtifactRepository,
    )

    repository = SQLiteLearningArtifactRepository(db_path)
    analyze = AnalyzePreOpenUseCase(
        observations=repository,
        tracks=repository,
        pre_open_config=load_pre_open_screen_config(),
        clock_date=datetime.now(IDX_TIMEZONE).date(),
    )
    csv_store = PreOpenPaperJournalCsvStore(journal)
    jsonl_store = TradeJournalJsonlWriter(journal.parent / "trades.jsonl")
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
                journal_path=journal,
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
