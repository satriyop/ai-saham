"""
CLI implementation for saham trade accum log/review (paper notebook).

Public registration: `saham trade accum log|review` via trade_commands.

Layer: Adapter
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_accum_workflow_factory import create_log_accumulation_trade_workflow
from src.application.use_case.evaluate_swing_setup_use_case import FOREIGN_BOUNCE_SETUP
from src.application.use_case.log_accumulation_trade_workflow_use_case import (
    LogAccumulationTradeWorkflowRequest,
)
from src.infrastructure.config.app_config import load_app_config


def run_accumulation_log_command(
    ticker: str,
    window: int,
    entry_price: Optional[float],
    from_analysis: bool,
    setup: str,
    with_regime: bool,
    regime_universe: Optional[str],
    benchmark: str,
    journal_path: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Public helper to run the log accumulation workflow and format CLI output."""
    cfg = load_app_config()
    resolved_journal = journal_path or Path(cfg.storage.accum_journal)
    resolved_db = db_path or Path(cfg.storage.db_path)

    bundle = create_log_accumulation_trade_workflow(
        db_path=resolved_db,
        journal_path=resolved_journal,
        with_regime=with_regime,
        regime_universe=regime_universe,
        benchmark=benchmark,
    )

    # Print any warnings from factory to stderr
    for warning in bundle.warnings:
        typer.echo(warning, err=True)

    request = LogAccumulationTradeWorkflowRequest(
        ticker=ticker,
        window=window,
        entry_price=Decimal(str(entry_price)) if entry_price is not None else None,
        from_analysis=from_analysis,
        setup=setup,
        with_regime=with_regime,
        benchmark=benchmark,
        logged_at=date.today(),
    )

    try:
        workflow_result = bundle.workflow.execute(request)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    result = workflow_result.response
    ticker_upper = result.ticker
    logged_at = workflow_result.logged_at
    setup_name = workflow_result.setup_name

    if result.candidate_accum_score is None and entry_price is None:
        typer.echo(
            f"Warning: no accumulation data for {ticker_upper} in "
            f"the last {window} broker sessions. "
            "Logging without a foreign-flow score.",
            err=True,
        )

    if not result.written:
        typer.echo(
            f"Already logged {ticker_upper} for {logged_at} (window={window} sessions) — "
            f"no new row added ({resolved_journal})"
        )
        return

    score_str = (
        f"{result.candidate_accum_score:.1f}" if result.candidate_accum_score is not None else "N/A"
    )
    pattern_str = f" | pattern: {result.pattern}" if result.pattern else ""
    decision_str = f" | setup={setup_name} | match={result.setup_match}" if from_analysis else ""
    plan_str = (
        f" | plan entry={result.entry_price:,.0f} stop={result.planned_stop:,.0f} "
        f"target={result.planned_target:,.0f} hold={workflow_result.max_hold_days}d"
        if from_analysis and result.planned_stop is not None and result.planned_target is not None
        else ""
    )
    regime_str = f" | regime={result.regime}" if result.regime else ""
    typer.echo(
        f"Logged {ticker_upper} | {logged_at} | window={window} sessions | "
        f"score={score_str}{pattern_str}{decision_str}{regime_str}{plan_str} → {resolved_journal}"
    )
    if from_analysis and result.failed_gates:
        typer.echo("Failed gates:")
        for gate in result.failed_gates:
            typer.echo(f"  - {gate}")


def accumulation_log(
    ticker: Annotated[
        str,
        typer.Option("--ticker", "-t", help="Ticker symbol to log (e.g. BBRI)"),
    ],
    window: Annotated[
        int,
        typer.Option("--window", "-w", help="Accumulation window in broker sessions", min=3),
    ] = 7,
    entry_price: Annotated[
        Optional[float],
        typer.Option("--entry-price", help="Entry price override (default = latest close)"),
    ] = None,
    from_analysis: Annotated[
        bool,
        typer.Option(
            "--from-analysis",
            help="Record setup match, failed gates, and trade plan fields",
        ),
    ] = False,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to journal with --from-analysis"),
    ] = FOREIGN_BOUNCE_SETUP,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Include market regime label in journal row"),
    ] = False,
    regime_universe: Annotated[
        Optional[str],
        typer.Option("--regime-universe", help="Universe for regime breadth"),
    ] = "lq45",
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = "IHSG",
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Journal CSV path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Log an accumulation candidate to the trade journal.

    Runs the accumulation screen for TICKER and appends one row to the
    journal CSV. Idempotent: re-running for the same (date, ticker, window)
    never duplicates rows.

    Example:
        saham trade accum log --ticker BBRI --window 7
        saham trade accum log --ticker BBCA --entry-price 9450
        saham trade accum log --ticker BBRI --from-analysis --with-regime
    """
    run_accumulation_log_command(
        ticker=ticker,
        window=window,
        entry_price=entry_price,
        from_analysis=from_analysis,
        setup=setup,
        with_regime=with_regime,
        regime_universe=regime_universe,
        benchmark=benchmark,
        journal_path=journal,
        db_path=db_path,
    )


def accumulation_review(
    horizon: Annotated[
        int,
        typer.Option("--horizon", help="Trading days forward for max/min window", min=1),
    ] = 10,
    min_accum_score: Annotated[
        float,
        typer.Option(
            "--min-foreign-flow-score",
            help="Only include entries with foreign-flow score >= this",
        ),
    ] = 0.0,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Journal CSV path"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Review accumulation trade journal: forward returns by foreign-flow score and pattern.

    Fetches actual forward closes from the local database and computes
    what the foreign-flow score thresholds actually delivered.

    Example:
        saham trade accum review
        saham trade accum review --horizon 10 --min-foreign-flow-score 70
    """
    from src.adapters.cli.trade_accum_workflow_factory import (
        create_accumulation_journal_service,
    )

    cfg = load_app_config()
    journal_path = journal or Path(cfg.storage.accum_journal)
    resolved_db = db_path or Path(cfg.storage.db_path)

    if not journal_path.exists():
        typer.echo(
            f"No journal found at '{journal_path}'.\n"
            "Run `saham trade accum log --ticker BBRI` first.",
            err=True,
        )
        raise typer.Exit(1)

    service = create_accumulation_journal_service(
        db_path=resolved_db,
        journal_path=journal_path,
    )

    typer.echo(f"Reviewing journal ({journal_path}) | horizon={horizon}d ...")
    report = service.review(horizon_days=horizon)

    from src.adapters.cli.trade_accum_display import display_journal_review

    display_journal_review(
        report=report,
        journal_path=journal_path,
        horizon=horizon,
        min_accum_score=min_accum_score,
    )
