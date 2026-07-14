"""
CLI command for `saham analyze compare` — side-by-side multi-ticker comparison.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.analyze_risk_workflow_factory import create_run_risk_compare_workflow
from src.application.use_case.run_risk_compare_use_case import RunRiskCompareRequest
from src.infrastructure.config.app_config import load_app_config

__all__ = ["compare"]


def compare(
    tickers: Annotated[
        list[str], typer.Argument(help="Two or more tickers to compare (e.g., BBCA BBRI BMRI)")
    ],
    sma_period: Annotated[int, typer.Option("--sma", help="SMA period", min=1)] = 20,
    rsi_period: Annotated[int, typer.Option("--rsi", help="RSI period", min=1)] = 14,
    days: Annotated[int, typer.Option("--days", "-d", help="Days of history", min=30)] = 365,
    db_path: Annotated[Optional[Path], typer.Option("--db", help="SQLite database path")] = None,
) -> None:
    """
    Side-by-side risk comparison for multiple IDX tickers.

    Requires cached data for each ticker (`saham fetch market TICKERS` first).

    Examples:
        saham analyze compare BBCA BBRI BMRI
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    try:
        workflow = create_run_risk_compare_workflow(resolved_db)
        result = workflow.execute(
            RunRiskCompareRequest(
                tickers=tickers,
                sma_period=sma_period,
                rsi_period=rsi_period,
                days=days,
            )
        )
    except ValueError as e:
        typer.echo(f"[error] {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n{'=' * 60}")
    typer.echo(" Risk Comparison")
    typer.echo(f"{'=' * 60}\n")
    typer.echo(
        f"{'TICKER':<8} {'CLOSE':>10} {'SMA({})'.format(sma_period):>10}"
        f" {'RSI({})'.format(rsi_period):>9} {'RISK':<12} {'CONF':>6}"
    )
    typer.echo("─" * 60)

    for row in result.rows:
        if row.has_data:
            close_display = f"{row.close:,.0f}" if row.close is not None else "—"
            typer.echo(
                f"{row.ticker:<8} {close_display:>10} {float(row.sma):>10,.0f}"
                f" {float(row.rsi):>9.1f} {row.risk_level_name:<12} {row.confidence:>4}/100"
            )
        else:
            typer.echo(
                f"{row.ticker:<8} {'—':>10} {'—':>10} {'—':>9} {'NO DATA':<12} {'—':>6}"
            )

    typer.echo("─" * 60)
    typer.echo("\nDISCLAIMER: Analysis only, not trading advice.")
