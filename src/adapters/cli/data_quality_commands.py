"""
Data quality audit CLI.

Layer: Adapter
"""

from pathlib import Path
from typing import Annotated

import typer

from src.application.use_case.data_quality_audit import (
    DataQualityAuditRequest,
    DataQualityAuditUseCase,
    DataQualityIssue,
    DataQualityTableSnapshot,
)
from src.infrastructure.persistence.sqlite_data_quality_audit import (
    SQLiteDataQualityAuditReader,
)

DEFAULT_DB_PATH = Path("data.db")


def data_quality_audit(
    tickers: Annotated[
        list[str] | None,
        typer.Argument(help="Optional ticker scope, e.g. BBCA BBRI"),
    ] = None,
    db_path: Annotated[
        Path,
        typer.Option("--db", help="SQLite database path"),
    ] = DEFAULT_DB_PATH,
) -> None:
    """
    Audit local data quality without network access or data mutation.
    """
    response = DataQualityAuditUseCase(
        SQLiteDataQualityAuditReader(db_path)
    ).execute(DataQualityAuditRequest(tickers=tickers))

    color = {
        "pass": typer.colors.GREEN,
        "warn": typer.colors.YELLOW,
        "fail": typer.colors.RED,
    }.get(response.status, typer.colors.WHITE)

    typer.echo("")
    typer.echo(typer.style("Data Quality Audit", fg=color, bold=True))
    typer.echo(f"Status: {response.status.upper()}")
    typer.echo(f"Expected trading day: {response.expected_trading_day or '-'}")
    typer.echo(f"Issues: {response.fail_count} fail, {response.warn_count} warn")

    if response.core_tables:
        typer.echo("")
        typer.echo("Core tables")
        _print_tables(response.core_tables)

    if response.enrichment_tables:
        typer.echo("")
        typer.echo("Enrichment tables")
        _print_tables(response.enrichment_tables)

    if response.issues:
        typer.echo("")
        typer.echo("Findings")
        for issue in response.issues:
            _print_issue(issue)
    else:
        typer.echo("")
        typer.echo(typer.style("No quality issues detected.", fg=typer.colors.GREEN))


def _print_tables(tables: tuple[DataQualityTableSnapshot, ...]) -> None:
    typer.echo(
        f"  {'TABLE':<28} {'ROWS':>9} {'TICKERS':>7} "
        f"{'LATEST':<12} {'STALE':>5} {'MISS':>5}"
    )
    for table in tables:
        latest = table.latest.isoformat() if table.latest else "-"
        typer.echo(
            f"  {table.table:<28} {table.rows:>9,} {table.tickers:>7,} "
            f"{latest:<12} {table.stale_tickers:>5} {table.missing_tickers:>5}"
        )


def _print_issue(issue: DataQualityIssue) -> None:
    color = {
        "fail": typer.colors.RED,
        "warn": typer.colors.YELLOW,
        "info": typer.colors.CYAN,
    }.get(issue.severity, typer.colors.WHITE)
    typer.echo(typer.style(f"  [{issue.severity.upper()}] {issue.code}", fg=color))
    typer.echo(f"    {issue.message}")
    typer.echo(f"    Impact: {issue.impact}")
