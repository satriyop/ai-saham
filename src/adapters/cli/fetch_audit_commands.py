"""
CLI implementation for saham fetch audit command.
Public command registration lives in lifecycle routers:
  saham fetch audit
Layer: Adapter
"""

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.application.use_case.data_quality_audit_use_case import (
    DataQualityAuditRequest,
    DataQualityAuditUseCase,
    DataQualityIssue,
    DataQualityTableSnapshot,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_data_quality_audit import (
    SQLiteDataQualityAuditReader,
)


def data_quality_audit(
    tickers: Annotated[
        list[str] | None,
        typer.Argument(help="Optional ticker scope, e.g. BBCA BBRI"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
) -> None:
    """
    Audit local data quality without network access or data mutation.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    response = DataQualityAuditUseCase(SQLiteDataQualityAuditReader(resolved_db)).execute(
        DataQualityAuditRequest(tickers=tickers)
    )

    console = Console()

    color = {
        "pass": "green",
        "warn": "yellow",
        "fail": "red",
    }.get(response.status, "white")

    console.print("")
    status_text = Text()
    status_text.append("Status: ", style="bold")
    status_text.append(response.status.upper(), style=f"bold {color}")
    status_text.append(f" | Expected trading day: {response.expected_trading_day or '-'}")
    status_text.append(f" | Issues: {response.fail_count} fail, {response.warn_count} warn")

    panel = Panel(
        status_text,
        title="[bold]Data Quality Audit[/bold]",
        border_style=color,
        expand=False,
    )
    console.print(panel)

    if response.core_tables:
        console.print("")
        console.print("[bold]Core Tables[/bold]")
        _print_tables(console, response.core_tables)

    if response.enrichment_tables:
        console.print("")
        console.print("[bold]Enrichment Tables[/bold]")
        _print_tables(console, response.enrichment_tables)

    if response.issues:
        console.print("")
        console.print("[bold red]Findings[/bold red]")
        for issue in response.issues:
            _print_issue(console, issue)
    else:
        console.print("")
        console.print("[green]✓ No quality issues detected.[/green]")
    console.print("")


def _print_tables(console: Console, tables: tuple[DataQualityTableSnapshot, ...]) -> None:
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Table", style="cyan")
    table.add_column("Rows", justify="right")
    table.add_column("Tickers", justify="right")
    table.add_column("Latest Update", justify="left")
    table.add_column("Stale Tickers", justify="right")
    table.add_column("Missing Tickers", justify="right")

    for t in tables:
        latest = t.latest.isoformat() if t.latest else "-"

        # Style stale/missing tickers if > 0
        stale_style = "red" if t.stale_tickers > 0 else "green"
        missing_style = "red" if t.missing_tickers > 0 else "green"

        stale_val = f"[{stale_style}]{t.stale_tickers}[/{stale_style}]"
        missing_val = f"[{missing_style}]{t.missing_tickers}[/{missing_style}]"

        table.add_row(
            t.table,
            f"{t.rows:,}",
            f"{t.tickers:,}",
            latest,
            stale_val,
            missing_val,
        )
    console.print(table)


def _print_issue(console: Console, issue: DataQualityIssue) -> None:
    color = {
        "fail": "red",
        "warn": "yellow",
        "info": "cyan",
    }.get(issue.severity, "white")

    console.print(
        f"  [bold {color}][{issue.severity.upper()}][/bold {color}] [bold]{issue.code}[/bold]"
    )
    console.print(f"    [dim]Message:[/dim] {issue.message}")
    console.print(f"    [dim]Impact:[/dim]  {issue.impact}")
