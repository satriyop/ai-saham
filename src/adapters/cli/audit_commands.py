"""
CLI implementation for saham audit data commands.
Public command registration lives in lifecycle routers:
  saham audit data manifest
  saham audit data source-contracts
  saham audit data reconcile-sources
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

from src.application.use_case.audit_source_field_contracts_use_case import (
    AuditSourceFieldContractsResponse,
    AuditSourceFieldContractsUseCase,
)
from src.application.use_case.audit_source_reconciliation_use_case import (
    AuditSourceReconciliationResponse,
    AuditSourceReconciliationUseCase,
)
from src.application.use_case.build_audit_baseline_manifest_use_case import (
    AuditBaselineManifest,
    BuildAuditBaselineManifestRequest,
    BuildAuditBaselineManifestUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.audit_config_identity_reader import (
    FileAuditConfigIdentityReader,
)
from src.infrastructure.config.audit_validation_panel_reader import (
    YamlAuditValidationPanelReader,
)
from src.infrastructure.config.git_code_identity_provider import GitCodeIdentityProvider
from src.infrastructure.persistence.source_field_contract_catalog import (
    StaticSourceFieldContractCatalog,
)
from src.infrastructure.persistence.sqlite_audit_manifest_reader import (
    SQLiteAuditManifestReader,
)
from src.infrastructure.persistence.sqlite_enrichment_reconciliation_reader import (
    SQLiteEnrichmentReconciliationReader,
)
from src.infrastructure.persistence.sqlite_signal_artifact_reconciliation_reader import (
    SQLiteSignalArtifactReconciliationReader,
)
from src.infrastructure.persistence.sqlite_source_field_contract_reader import (
    SQLiteSourceFieldContractReader,
)
from src.infrastructure.persistence.sqlite_source_reconciliation_reader import (
    SQLiteSourceReconciliationReader,
)

_VALID_FORMATS = ("table", "json")

data_app = typer.Typer(
    name="data",
    help=(
        "Read-only data-quality audit artifacts (baseline manifest, source-field "
        "contracts, source reconciliation)."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

audit_app = typer.Typer(
    name="audit",
    help="Read-only audits — data-quality baseline manifest and source-field contracts.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def manifest(
    tickers: Annotated[
        list[str] | None,
        typer.Argument(help="Optional ticker scope, e.g. BBCA BBRI"),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json."),
    ] = "table",
) -> None:
    """
    Emit a read-only DQ-000 audit baseline manifest (database/config/code identity).
    """
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    _run_manifest(tickers=tickers, db_path=db_path, output_format=output_format)


def source_contracts(
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json."),
    ] = "table",
) -> None:
    """
    Emit a read-only DQ-001A source-field contract audit for core tables.
    """
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    _run_source_contracts(db_path=db_path, output_format=output_format)


def reconcile_sources(
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json."),
    ] = "table",
) -> None:
    """
    Emit a read-only DQ-001B source reconciliation audit (OHLC invariants,
    arithmetic identities, and cross-table foreign-flow overlaps).
    """
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    _run_reconcile_sources(db_path=db_path, output_format=output_format)


data_app.command("manifest")(manifest)
data_app.command("source-contracts")(source_contracts)
data_app.command("reconcile-sources")(reconcile_sources)
audit_app.add_typer(data_app, name="data")


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
    manifest_response = use_case.execute(
        BuildAuditBaselineManifestRequest(db_path=resolved_db, tickers=normalized_tickers)
    )

    if output_format == "json":
        typer.echo(json.dumps(manifest_response.to_dict(), indent=2, ensure_ascii=False))
        return

    _print_manifest_table(manifest_response)


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


def _run_source_contracts(db_path: Path | None, output_format: str) -> None:
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    catalog = StaticSourceFieldContractCatalog()
    use_case = AuditSourceFieldContractsUseCase(
        reader=SQLiteSourceFieldContractReader(resolved_db, catalog=catalog),
        catalog=catalog,
    )
    response = use_case.execute()

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
        return

    _print_source_contracts_table(response)


def _print_source_contracts_table(response: AuditSourceFieldContractsResponse) -> None:
    console = Console()
    color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(response.status, "white")

    console.print("")
    status_text = Text()
    status_text.append("Status: ", style="bold")
    status_text.append(response.status, style=f"bold {color}")
    status_text.append(f" | Findings: {len(response.findings)}")
    panel = Panel(
        status_text,
        title="[bold]Source Field Contract Audit (DQ-001A)[/bold]",
        border_style=color,
        expand=False,
    )
    console.print(panel)

    if response.tables:
        console.print("")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Table", style="cyan")
        table.add_column("Exists", justify="center")
        table.add_column("Rows", justify="right")
        table.add_column("Status", justify="center")
        table.add_column("Fields FAIL/WARN", justify="right")
        for t in response.tables:
            fail_count = sum(1 for f in t.fields if f.status == "FAIL")
            warn_count = sum(1 for f in t.fields if f.status == "WARN")
            status_color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(
                t.contract_status, "white"
            )
            table.add_row(
                t.table,
                str(t.exists),
                f"{t.row_count:,}" if t.row_count is not None else "-",
                f"[{status_color}]{t.contract_status}[/{status_color}]",
                f"{fail_count}/{warn_count}",
            )
        console.print(table)

    if response.findings:
        console.print("")
        console.print("[bold red]Findings[/bold red]")
        for finding in response.findings:
            _print_source_contract_finding(console, finding)
    else:
        console.print("")
        console.print("[green]✓ No source-contract findings.[/green]")
    console.print("")


def _print_source_contract_finding(console: Console, finding) -> None:
    color = {"FAIL": "red", "WARN": "yellow", "INFO": "cyan"}.get(finding.severity, "white")
    field_suffix = f".{finding.field}" if finding.field else ""
    console.print(
        f"  [bold {color}][{finding.severity}][/bold {color}] "
        f"[bold]{finding.code}[/bold] ({finding.table}{field_suffix})"
    )
    console.print(f"    [dim]Message:[/dim] {finding.message}")
    console.print(f"    [dim]Impact:[/dim]  {finding.impact}")


def _run_reconcile_sources(db_path: Path | None, output_format: str) -> None:
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    use_case = AuditSourceReconciliationUseCase(
        reader=SQLiteSourceReconciliationReader(resolved_db),
        enrichment_reader=SQLiteEnrichmentReconciliationReader(resolved_db),
        artifact_reader=SQLiteSignalArtifactReconciliationReader(resolved_db),
    )
    response = use_case.execute()

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
        return

    _print_reconcile_sources_table(response)


def _print_reconcile_sources_table(response: AuditSourceReconciliationResponse) -> None:
    console = Console()
    color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(response.status, "white")

    console.print("")
    status_text = Text()
    status_text.append("Status: ", style="bold")
    status_text.append(response.status, style=f"bold {color}")
    status_text.append(f" | Findings: {len(response.findings)}")
    panel = Panel(
        status_text,
        title="[bold]Source Reconciliation Audit (DQ-001B/DQ-001D/DQ-001E)[/bold]",
        border_style=color,
        expand=False,
    )
    console.print(panel)

    if response.checks:
        console.print("")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Check", style="cyan")
        table.add_column("Tables")
        table.add_column("Checked Rows", justify="right")
        table.add_column("Mismatches", justify="right")
        table.add_column("Status", justify="center")
        for c in response.checks:
            status_color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(
                c.status, "white"
            )
            table.add_row(
                c.name,
                ", ".join(c.tables),
                f"{c.checked_row_count:,}" if c.checked_row_count is not None else "-",
                str(c.mismatch_count) if c.mismatch_count is not None else "-",
                f"[{status_color}]{c.status}[/{status_color}]",
            )
        console.print(table)

    if response.findings:
        console.print("")
        console.print("[bold red]Findings[/bold red]")
        for finding in response.findings:
            _print_source_contract_finding(console, finding)
    else:
        console.print("")
        console.print("[green]✓ No reconciliation findings.[/green]")
    console.print("")
