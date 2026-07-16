"""
CLI implementation for saham audit data commands.
Public command registration lives in lifecycle routers:
  saham audit data manifest
  saham audit data source-contracts
  saham audit data reconcile-sources
  saham audit data contract-gate
  saham audit data seasonality-cleanup-plan
  saham audit data candidate-observation-identity
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
from src.application.use_case.build_dq_contract_gate_use_case import (
    BuildDQContractGateUseCase,
    DQContractGateResponse,
)
from src.application.use_case.build_seasonality_cleanup_plan_use_case import (
    BuildSeasonalityCleanupPlanUseCase,
    SeasonalityCleanupPlanResponse,
)
from src.application.use_case.audit_candidate_observation_identity_use_case import (
    AuditCandidateObservationIdentityUseCase,
    CandidateObservationIdentityAuditResponse,
)
from src.application.use_case.repair_seasonality_cache_use_case import (
    RepairSeasonalityCacheResponse,
    RepairSeasonalityCacheUseCase,
)
from src.infrastructure.persistence.sqlite_seasonality_cache_repairer import (
    SQLiteSeasonalityCacheRepairer,
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
from src.infrastructure.persistence.sqlite_seasonality_cleanup_plan_reader import (
    SQLiteSeasonalityCleanupPlanReader,
)
from src.infrastructure.persistence.sqlite_candidate_observation_identity_reader import (
    SQLiteCandidateObservationIdentityReader,
)
from src.infrastructure.persistence.sqlite_source_reconciliation_reader import (
    SQLiteSourceReconciliationReader,
)

_VALID_FORMATS = ("table", "json")

data_app = typer.Typer(
    name="data",
    help=(
        "Data-quality audit artifacts (baseline manifest, source-field "
        "contracts, source reconciliation, repair commands)."
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


def contract_gate(
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
    Evaluate the DQ-CONTRACT-GATE: combine the source-contracts and
    reconcile-sources audits into one PASS/FAIL gate and exit non-zero on
    FAIL. WARN on either audit is treated as a gate failure (fail closed).
    """
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    _run_contract_gate(db_path=db_path, output_format=output_format)


def seasonality_cleanup_plan(
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
    Emit a read-only DQ-001G dry-run cleanup plan for invalid seasonality_cache
    rows. Report command only: never mutates the database, always exits 0.
    """
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    _run_seasonality_cleanup_plan(db_path=db_path, output_format=output_format)


def repair_seasonality_cache(
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Dry-run mode: report only, no mutation."),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Apply mode: quarantine and delete invalid rows."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json."),
    ] = "json",
) -> None:
    """
    Repair invalid seasonality_cache rows by quarantining them (DQ-001H).

    Default is dry-run: reports which rows would be quarantined without
    mutating the database.  Use --apply to perform the quarantine.

    Never deletes rows without quarantining them first.  The quarantine
    table preserves the full original row plus reasons, repair_run_id, and
    a timestamp.
    """
    if dry_run and apply:
        raise typer.BadParameter(
            "Cannot use both --dry-run and --apply. "
            "Default (no flag) is dry-run."
        )
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    _run_repair_seasonality_cache(
        db_path=db_path, apply=apply, output_format=output_format
    )


def candidate_observation_identity(
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="SQLite database path"),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json."),
    ] = "json",
) -> None:
    """
    Read-only DQ-001I identity audit for candidate_observations.

    Reports how many rows are legacy (empty config_hash), how many are
    canonical, whether the latest snapshot depends on legacy rows, and
    whether duplicate identity groups exist among canonical rows.
    Report command only — always exits 0, never mutates the database.
    """
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    _run_candidate_observation_identity(db_path=db_path, output_format=output_format)


data_app.command("manifest")(manifest)
data_app.command("source-contracts")(source_contracts)
data_app.command("reconcile-sources")(reconcile_sources)
data_app.command("contract-gate")(contract_gate)
data_app.command("seasonality-cleanup-plan")(seasonality_cleanup_plan)
data_app.command("repair-seasonality-cache")(repair_seasonality_cache)
data_app.command("candidate-observation-identity")(candidate_observation_identity)
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


def _run_contract_gate(db_path: Path | None, output_format: str) -> None:
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    catalog = StaticSourceFieldContractCatalog()
    source_contracts_use_case = AuditSourceFieldContractsUseCase(
        reader=SQLiteSourceFieldContractReader(resolved_db, catalog=catalog),
        catalog=catalog,
    )
    source_reconciliation_use_case = AuditSourceReconciliationUseCase(
        reader=SQLiteSourceReconciliationReader(resolved_db),
        enrichment_reader=SQLiteEnrichmentReconciliationReader(resolved_db),
        artifact_reader=SQLiteSignalArtifactReconciliationReader(resolved_db),
    )
    use_case = BuildDQContractGateUseCase(
        source_contracts_use_case=source_contracts_use_case,
        source_reconciliation_use_case=source_reconciliation_use_case,
    )
    response = use_case.execute()

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_contract_gate_table(response)

    if response.status != "PASS":
        raise typer.Exit(code=1)


def _print_contract_gate_table(response: DQContractGateResponse) -> None:
    console = Console()
    color = {"PASS": "green", "FAIL": "red"}.get(response.status, "white")
    sub_color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}

    console.print("")
    status_text = Text()
    status_text.append("Gate Status: ", style="bold")
    status_text.append(response.status, style=f"bold {color}")
    status_text.append(f" | Blockers: {len(response.blockers)}")
    panel = Panel(
        status_text,
        title="[bold]DQ Contract Gate[/bold]",
        border_style=color,
        expand=False,
    )
    console.print(panel)

    summary = Table(show_header=True, header_style="bold magenta")
    summary.add_column("Audit")
    summary.add_column("Status", justify="center")
    contract_color = sub_color.get(response.source_contract_status, "white")
    reconciliation_color = sub_color.get(response.source_reconciliation_status, "white")
    summary.add_row(
        "source-contracts",
        f"[{contract_color}]{response.source_contract_status}[/{contract_color}]",
    )
    summary.add_row(
        "reconcile-sources",
        f"[{reconciliation_color}]{response.source_reconciliation_status}"
        f"[/{reconciliation_color}]",
    )
    console.print(summary)

    if response.blockers:
        console.print("")
        console.print("[bold red]Blockers[/bold red]")
        for blocker in response.blockers:
            blocker_color = {"FAIL": "red", "WARN": "yellow"}.get(blocker.severity, "white")
            location = blocker.table or "-"
            if blocker.field:
                location += f".{blocker.field}"
            console.print(
                f"  [bold {blocker_color}][{blocker.severity}][/bold {blocker_color}] "
                f"[dim]({blocker.source})[/dim] [bold]{blocker.code}[/bold] ({location})"
            )
            console.print(f"    [dim]Message:[/dim] {blocker.message}")
    else:
        console.print("")
        console.print("[green]✓ DQ-CONTRACT-GATE passed — no blockers.[/green]")
    console.print("")


def _run_seasonality_cleanup_plan(db_path: Path | None, output_format: str) -> None:
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    use_case = BuildSeasonalityCleanupPlanUseCase(
        reader=SQLiteSeasonalityCleanupPlanReader(resolved_db),
    )
    response = use_case.execute()

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
        return

    _print_seasonality_cleanup_plan_table(response)

    # Report command, not a gate: always exits 0, even when status is FAIL.


def _print_seasonality_cleanup_plan_table(response: SeasonalityCleanupPlanResponse) -> None:
    console = Console()
    color = {"PASS": "green", "FAIL": "red"}.get(response.status, "white")

    console.print("")
    status_text = Text()
    status_text.append("Status: ", style="bold")
    status_text.append(response.status, style=f"bold {color}")
    status_text.append(f" | Invalid rows: {response.invalid_row_count}")
    status_text.append(" | Dry run — no mutation performed", style="dim")
    panel = Panel(
        status_text,
        title="[bold]Seasonality Cleanup Plan (DQ-001G, dry-run)[/bold]",
        border_style=color,
        expand=False,
    )
    console.print(panel)

    if not response.source_available:
        console.print("")
        reason_message = {
            "DATABASE_MISSING": "the SQLite database file could not be found",
            "SEASONALITY_CACHE_TABLE_MISSING": (
                "the database exists but has no seasonality_cache table"
            ),
        }.get(response.source_unavailable_reason or "", "the source is unavailable")
        console.print(
            f"[bold red]⚠ seasonality_cache is unavailable[/bold red] "
            f"([{response.source_unavailable_reason}]) — {reason_message}. "
            "Check --db before trusting this report; PASS is impossible to "
            "reach until the table is readable."
        )

    console.print("")
    reason_table = Table(show_header=True, header_style="bold magenta")
    reason_table.add_column("Reason", style="cyan")
    reason_table.add_column("Count", justify="right")
    for reason, count in response.invalid_reason_counts.items():
        reason_table.add_row(reason, str(count))
    console.print(reason_table)

    if response.rows:
        console.print("")
        console.print(f"[bold]Proposed action:[/bold] {response.proposed_action} (not executed)")
        console.print("")
        rows_table = Table(show_header=True, header_style="bold magenta")
        rows_table.add_column("Ticker", style="cyan")
        rows_table.add_column("Year", justify="right")
        rows_table.add_column("Month", justify="right")
        rows_table.add_column("Fetched At")
        rows_table.add_column("Source")
        rows_table.add_column("Reasons")
        for row in response.rows:
            rows_table.add_row(
                row.ticker,
                str(row.year),
                str(row.month),
                row.fetched_at or "-",
                row.source or "-",
                ", ".join(row.reasons),
            )
        console.print(rows_table)
    elif response.source_available:
        console.print("")
        console.print("[green]✓ No invalid seasonality_cache rows found.[/green]")
    console.print("")


def _run_repair_seasonality_cache(
    db_path: Path | None,
    apply: bool,
    output_format: str,
) -> None:
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    use_case = RepairSeasonalityCacheUseCase(
        reader=SQLiteSeasonalityCleanupPlanReader(resolved_db),
        repairer=SQLiteSeasonalityCacheRepairer(resolved_db),
    )
    response = use_case.execute(dry_run=not apply)

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
        return

    _print_seasonality_cache_repair_table(response)


def _print_seasonality_cache_repair_table(response: RepairSeasonalityCacheResponse) -> None:
    console = Console()
    mode_color = {"DRY_RUN": "yellow", "APPLY": "red" if response.status == "FAIL" else "green"}
    color = {"PASS": "green", "FAIL": "red"}.get(response.status, "white")

    console.print("")
    status_text = Text()
    status_text.append("Mode: ", style="bold")
    status_text.append(response.mode, style=f"bold {mode_color.get(response.mode, 'white')}")
    status_text.append("  |  Status: ", style="bold")
    status_text.append(response.status, style=f"bold {color}")
    status_text.append(f"  |  Invalid rows: {response.invalid_row_count}")
    if response.dry_run:
        status_text.append("  |  Dry run — no mutation performed", style="dim")
    panel = Panel(
        status_text,
        title="[bold]Seasonality Cache Repair (DQ-001H)[/bold]",
        border_style=color,
        expand=False,
    )
    console.print(panel)

    if not response.source_available:
        console.print("")
        reason_message = {
            "DATABASE_MISSING": "the SQLite database file could not be found",
            "SEASONALITY_CACHE_TABLE_MISSING": (
                "the database exists but has no seasonality_cache table"
            ),
        }.get(response.source_unavailable_reason or "", "the source is unavailable")
        console.print(
            f"[bold red]⚠ seasonality_cache is unavailable[/bold red] "
            f"([{response.source_unavailable_reason}]) — {reason_message}. "
            "Check --db before trusting this report."
        )

    console.print("")
    info_table = Table(show_header=True, header_style="bold magenta")
    info_table.add_column("Measure", style="cyan")
    info_table.add_column("Value", justify="right")
    info_table.add_row("Repair run ID", response.repair_run_id)
    info_table.add_row("Invalid rows", str(response.invalid_row_count))
    info_table.add_row("Quarantined rows", str(response.quarantined_row_count))
    info_table.add_row("Deleted rows", str(response.deleted_row_count))
    console.print(info_table)

    console.print("")
    reason_table = Table(show_header=True, header_style="bold magenta")
    reason_table.add_column("Reason", style="cyan")
    reason_table.add_column("Count", justify="right")
    for reason, count in response.reason_counts.items():
        if count > 0:
            reason_table.add_row(reason, str(count))
    console.print(reason_table)

    if response.rows:
        console.print("")
        console.print("[bold]Invalid rows:[/bold]")
        console.print("")
        rows_table = Table(show_header=True, header_style="bold magenta")
        rows_table.add_column("Ticker", style="cyan")
        rows_table.add_column("Year", justify="right")
        rows_table.add_column("Month", justify="right")
        rows_table.add_column("Fetched At")
        rows_table.add_column("Source")
        rows_table.add_column("Reasons")
        for row in response.rows:
            rows_table.add_row(
                row.ticker,
                str(row.year),
                str(row.month),
                row.fetched_at or "-",
                row.source or "-",
                ", ".join(row.reasons),
            )
        console.print(rows_table)

    if response.dry_run and response.source_available:
        console.print("")
        console.print("[yellow]⚠ Dry-run: no mutation performed.[/yellow]")
    elif response.source_available and response.invalid_row_count > 0 and not response.dry_run:
        console.print("")
        console.print(
            f"[green]✓ Quarantined and deleted {response.quarantined_row_count} "
            f"invalid row(s).[/green]"
        )
    elif response.source_available and response.invalid_row_count == 0:
        console.print("")
        console.print("[green]✓ No invalid seasonality_cache rows found.[/green]")
    console.print("")


def _run_candidate_observation_identity(
    db_path: Path | None,
    output_format: str,
) -> None:
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    use_case = AuditCandidateObservationIdentityUseCase(
        reader=SQLiteCandidateObservationIdentityReader(resolved_db),
    )
    response = use_case.execute()

    if output_format == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
        return

    _print_candidate_observation_identity_table(response)


def _print_candidate_observation_identity_table(
    response: CandidateObservationIdentityAuditResponse,
) -> None:
    console = Console()
    color = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}.get(response.status, "white")
    rec_color = {"NO_ACTION": "green", "QUARANTINE_SAFE": "yellow", "REBUILD_REQUIRED": "red"}.get(
        response.recommendation, "white"
    )

    console.print("")
    status_text = Text()
    status_text.append("Status: ", style="bold")
    status_text.append(response.status, style=f"bold {color}")
    status_text.append(f" | Recommendation: ", style="bold")
    status_text.append(response.recommendation, style=f"bold {rec_color}")
    panel = Panel(
        status_text,
        title="[bold]Candidate Observation Identity Audit (DQ-001I)[/bold]",
        border_style=color,
        expand=False,
    )
    console.print(panel)

    if not response.source_available:
        reason_message = {
            "DATABASE_MISSING": "the SQLite database file could not be found",
            "CANDIDATE_OBSERVATIONS_TABLE_MISSING": (
                "the database exists but has no candidate_observations table"
            ),
        }.get(response.source_unavailable_reason or "", "the source is unavailable")
        console.print("")
        console.print(
            f"[bold red]⚠ candidate_observations is unavailable[/bold red] "
            f"([{response.source_unavailable_reason}]) — {reason_message}. "
            "Check --db before trusting this report."
        )
        console.print("")
        return

    console.print("")
    summary = Table(show_header=True, header_style="bold magenta")
    summary.add_column("Measure", style="cyan")
    summary.add_column("Value", justify="right")
    summary.add_row("Total rows", f"{response.total_row_count:,}")
    summary.add_row("Canonical rows", f"{response.canonical_row_count:,}")
    summary.add_row("Legacy rows", f"{response.legacy_row_count:,}")
    summary.add_row("Legacy ratio", f"{response.legacy_ratio:.2%}")
    summary.add_row("Duplicate identity groups", str(response.duplicate_identity_group_count))
    if response.latest_readiness_dependency.get("latest_snapshot_date"):
        dep = response.latest_readiness_dependency
        summary.add_row(
            "Latest snapshot",
            f"{dep['latest_snapshot_date']} "
            f"({dep['latest_total_rows']} rows, "
            f"{dep['latest_legacy_rows']} legacy)",
        )
    console.print(summary)

    if response.findings:
        console.print("")
        console.print("[bold]Findings[/bold]")
        for finding in response.findings:
            fcolor = {"FAIL": "red", "WARN": "yellow", "INFO": "cyan"}.get(
                finding.get("severity", ""), "white"
            )
            console.print(
                f"  [bold {fcolor}][{finding['severity']}][/bold {fcolor}] "
                f"[bold]{finding['code']}[/bold]"
            )
            if finding.get("message"):
                console.print(f"    {finding['message']}")
    console.print("")
