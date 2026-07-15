"""
CLI implementation for saham fetch audit command.
Public command registration lives in lifecycle routers:
  saham fetch audit
Layer: Adapter
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.application.use_case.build_audit_baseline_manifest_use_case import (
    AuditBaselineManifest,
    BuildAuditBaselineManifestRequest,
    BuildAuditBaselineManifestUseCase,
)
from src.application.use_case.data_quality_audit_use_case import (
    DataQualityAuditRequest,
    DataQualityAuditUseCase,
    DataQualityIssue,
    DataQualityTableSnapshot,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.audit_config_identity_reader import (
    FileAuditConfigIdentityReader,
)
from src.infrastructure.config.audit_validation_panel_reader import (
    YamlAuditValidationPanelReader,
)
from src.infrastructure.config.git_code_identity_provider import GitCodeIdentityProvider
from src.infrastructure.persistence.sqlite_audit_manifest_reader import (
    SQLiteAuditManifestReader,
)
from src.infrastructure.persistence.sqlite_data_quality_audit import (
    SQLiteDataQualityAuditReader,
)

_VALID_FORMATS = ("table", "json")


def data_quality_audit(
    tickers: Annotated[
        list[str] | None,
        typer.Argument(help="Optional ticker scope, e.g. BBCA BBRI"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    manifest: Annotated[
        bool,
        typer.Option(
            "--manifest",
            help="Emit a read-only DQ-000 audit baseline manifest instead of the quality audit.",
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format for --manifest: table or json."),
    ] = "table",
) -> None:
    """
    Audit local data quality without network access or data mutation.
    """
    if manifest:
        if output_format not in _VALID_FORMATS:
            raise typer.BadParameter(
                f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
            )
        _run_manifest(tickers=tickers, db_path=db_path, output_format=output_format)
        return

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    response = DataQualityAuditUseCase(
        SQLiteDataQualityAuditReader(resolved_db)
    ).execute(DataQualityAuditRequest(tickers=tickers))

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


def _run_manifest(
    tickers: list[str] | None,
    db_path: Path | None,
    output_format: str,
) -> None:
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    normalized_tickers = tuple(t.upper().strip() for t in tickers or [] if t.strip())

    use_case = BuildAuditBaselineManifestUseCase(
        manifest_reader=SQLiteAuditManifestReader(resolved_db),
        config_reader=FileAuditConfigIdentityReader(),
        code_identity_provider=GitCodeIdentityProvider(),
        validation_panel_reader=YamlAuditValidationPanelReader(),
    )
    manifest = use_case.execute(
        BuildAuditBaselineManifestRequest(db_path=resolved_db, tickers=normalized_tickers)
    )

    if output_format == "json":
        typer.echo(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False))
        return

    _print_manifest_table(manifest)


def _print_manifest_table(manifest: AuditBaselineManifest) -> None:
    console = Console()
    console.print("")
    console.print(
        f"[bold]Audit Baseline Manifest[/bold]  "
        f"[dim]{manifest.artifact_type} v{manifest.schema_version}[/dim]"
    )
    console.print(f"Generated at: {manifest.generated_at}")

    summary = Table(show_header=True, header_style="bold magenta")
    summary.add_column("Field")
    summary.add_column("Value")
    summary.add_row("Database path", manifest.database.path)
    summary.add_row("Database exists", str(manifest.database.exists))
    summary.add_row("Database sha256", manifest.database.sha256 or "-")
    summary.add_row("Sqlite user_version", str(manifest.schema.sqlite_user_version))
    summary.add_row("Tables tracked", str(len(manifest.table_summaries)))
    summary.add_row("Git commit", manifest.code.git_commit or "-")
    summary.add_row("Git dirty", str(manifest.code.git_dirty))
    summary.add_row("Validation tickers", ", ".join(manifest.validation_scope.tickers) or "-")
    summary.add_row("Validation dates", ", ".join(manifest.validation_scope.dates) or "-")
    console.print(summary)

    if manifest.table_summaries:
        console.print("")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Table", style="cyan")
        table.add_column("Rows", justify="right")
        table.add_column("Min Date")
        table.add_column("Max Date")
        table.add_column("Tickers", justify="right")
        table.add_column("Duplicates", justify="right")
        for t in manifest.table_summaries:
            table.add_row(
                t.table,
                f"{t.row_count:,}",
                t.min_date or "-",
                t.max_date or "-",
                str(t.ticker_count) if t.ticker_count is not None else "-",
                str(t.duplicate_key_count) if t.duplicate_key_count is not None else "-",
            )
        console.print(table)

    if manifest.warnings:
        console.print("")
        console.print("[bold yellow]Warnings[/bold yellow]")
        for warning in manifest.warnings:
            console.print(f"  [yellow]- {warning}[/yellow]")
    console.print("")


def _print_issue(console: Console, issue: DataQualityIssue) -> None:
    color = {
        "fail": "red",
        "warn": "yellow",
        "info": "cyan",
    }.get(issue.severity, "white")

    console.print(f"  [bold {color}][{issue.severity.upper()}][/bold {color}] [bold]{issue.code}[/bold]")
    console.print(f"    [dim]Message:[/dim] {issue.message}")
    console.print(f"    [dim]Impact:[/dim]  {issue.impact}")
