"""
CLI implementation functions for swing tuning commands.

Layer: Adapter
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.trade_swing_display import display_swing_backtest
from src.adapters.cli.trade_swing_tuning_patch_writer import (
    write_swing_tuning_patch_export,
)
from src.adapters.cli.trade_swing_tuning_workflow_factory import (
    DEFAULT_SWING_TUNING_REVIEW_JOURNAL_PATH,
    create_run_swing_tuning_review_workflow,
)
from src.application.use_case.run_swing_tuning_review_use_case import (
    RunSwingTuningReviewRequest,
)
from src.application.use_case.swing_backtest_use_case import (
    FOREIGN_BOUNCE_SETUP as BACKTEST_FOREIGN_BOUNCE_SETUP,
)
from src.infrastructure.config.app_config import APP_CFG


def swing_tune(
    tickers: Annotated[
        Optional[list[str]],
        typer.Argument(help="Explicit ticker symbols (e.g. BBCA BBRI)"),
    ] = None,
    universe: Annotated[
        Optional[str],
        typer.Option(
            "--universe",
            "-u",
            help="Universe name or 'cached' — see `saham fetch universe list`",
        ),
    ] = None,
    setup: Annotated[
        str,
        typer.Option("--setup", help="Swing setup to validate"),
    ] = BACKTEST_FOREIGN_BOUNCE_SETUP,
    start: Annotated[
        str,
        typer.Option("--start", help="Backtest start date, YYYY-MM-DD"),
    ] = APP_CFG.backtest.start_date,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Backtest end date, YYYY-MM-DD (default: today)"),
    ] = None,
    capital: Annotated[
        Optional[int],
        typer.Option("--capital", "-c", help="Initial capital in IDR", min=1),
    ] = None,
    risk_pct: Annotated[
        Optional[float],
        typer.Option("--risk-pct", help="% of capital risked per trade", min=0.01),
    ] = None,
    max_positions: Annotated[
        Optional[int],
        typer.Option("--max-positions", help="Maximum concurrent open positions", min=1),
    ] = None,
    take_profit: Annotated[
        Optional[float],
        typer.Option("--take-profit", help="Take-profit percentage", min=0.01),
    ] = None,
    stop_loss: Annotated[
        Optional[float],
        typer.Option("--stop-loss", help="Stop-loss percentage", min=0.01),
    ] = None,
    max_hold: Annotated[
        Optional[int],
        typer.Option("--max-hold", help="Maximum holding period in trading days", min=1),
    ] = None,
    cost_bps: Annotated[
        Optional[float],
        typer.Option(
            "--cost-bps",
            help="One-way transaction cost in basis points (20 ~= 0.20%)",
            min=0,
        ),
    ] = None,
    with_regime: Annotated[
        bool,
        typer.Option("--with-regime", help="Group evidence by entry-date market regime"),
    ] = False,
    allow_regimes: Annotated[
        Optional[str],
        typer.Option(
            "--allow-regimes",
            help="Comma-separated entry regimes allowed to open trades",
        ),
    ] = None,
    benchmark: Annotated[
        str,
        typer.Option("--benchmark", help="Benchmark ticker for regime context"),
    ] = APP_CFG.analysis.benchmark,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = APP_CFG.analysis.format,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    save: Annotated[
        bool,
        typer.Option(
            "--save",
            help="Append the tuning review artifact to the local JSONL journal",
        ),
    ] = False,
    journal: Annotated[
        Optional[Path],
        typer.Option("--journal", help="Override swing tuning review journal path"),
    ] = None,
    export_patch: Annotated[
        Optional[Path],
        typer.Option(
            "--export-patch",
            help="Write proposed config values to a review-only JSON patch artifact",
        ),
    ] = None,
    is_ratio: Annotated[
        Optional[float],
        typer.Option(
            "--is-ratio",
            help=(
                "In-sample ratio 0.0–1.0 (e.g. 0.70 = 70% IS / 30% OOS). "
                "Default: 1.0 (no split)."
            ),
        ),
    ] = None,
) -> None:
    """
    Build deterministic swing tuning review from walk-forward attribution.

    This is the first-class tuning-loop entry point for swing. It replays the
    deterministic workflow, summarizes attribution, and emits guarded config
    review artifacts. It never calls AI and never writes YAML.
    """
    workflow = create_run_swing_tuning_review_workflow(journal_path=journal)
    request = RunSwingTuningReviewRequest(
        tickers=tickers,
        universe=universe,
        setup=setup,
        start=start,
        end=end,
        capital=capital,
        risk_pct=risk_pct,
        max_positions=max_positions,
        take_profit=take_profit,
        stop_loss=stop_loss,
        max_hold=max_hold,
        cost_bps=cost_bps,
        with_regime=with_regime,
        allow_regimes=allow_regimes,
        benchmark=benchmark,
        db_path=db_path,
        output_format=output_format,
        save=save,
        export_patch=export_patch is not None,
        is_ratio=is_ratio,
    )
    try:
        result = workflow.execute(request)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    payload = result.payload
    if save and result.persistence is not None:
        journal_path = journal or DEFAULT_SWING_TUNING_REVIEW_JOURNAL_PATH
        result.persistence["path"] = str(journal_path)
        payload["persistence"] = result.persistence

    if export_patch is not None and result.patch_payload is not None:
        patch_export = write_swing_tuning_patch_export(
            patch_payload=result.patch_payload,
            path=export_patch,
        )
        payload["patch_export"] = patch_export

    if output_format == "json":
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    if result.is_split_message:
        typer.echo(result.is_split_message)

    display_swing_backtest(
        result.response,
        show_trades=0,
        show_attribution=True,
        show_tuning_plan=True,
        show_tuning_proposal=True,
        show_tuning_diff=True,
    )
    if save and result.persistence is not None:
        persistence = payload["persistence"]
        typer.echo(
            f"Saved swing tuning review -> {persistence['path']} "
            f"(records={persistence['record_count']})"
        )
    if export_patch is not None:
        patch_export = payload["patch_export"]
        typer.echo(
            f"Exported swing tuning patch -> {patch_export['path']} "
            f"(items={patch_export['item_count']})"
        )
