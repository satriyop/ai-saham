"""
CLI commands for SignalEngine factor auditing.

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.ports.signal_coverage_provider import SignalCoverageReport
from src.application.services.bootstrap import resolve_signal_weight_tables
from src.application.use_case.audit_signal_use_case import (
    AuditSignalRequest,
    AuditSignalUseCase,
)
from src.domain.value_objects.signal_audit import SignalAuditReport
from src.infrastructure.composition.signal_engine_factory import create_signal_engine
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.signal_engine_config_loader import (
    load_signal_engine_config_raw,
)
from src.infrastructure.persistence.sqlite_signal_coverage_provider import (
    SqliteSignalCoverageProvider,
)

_FACTOR_LABELS = {
    "bandar_intensity": "bandar_intensity",
    "foreign_flow_quality": "foreign_flow_q…",
    "insider_activity": "insider_activity",
    "seasonality_edge": "seasonality_edge",
    "analyst_consensus": "analyst_consens…",
    "forward_valuation": "forward_valuati…",
}


def signal_audit(
    ticker: Annotated[str, typer.Argument(help="IDX ticker (e.g. BBCA)")],
    date_str: Annotated[
        Optional[str],
        typer.Option("--date", "-d", help="Snapshot date YYYY-MM-DD (default: today)"),
    ] = None,
    coverage: Annotated[
        bool,
        typer.Option("--coverage", help="Show DB-level factor coverage counts"),
    ] = False,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """
    Audit the archived six-factor signal baseline for one ticker.

    Shows archived factor presence, component scores, configured weights,
    weighted contributions, the archived neutral-fill baseline score, and an
    archived renormalized diagnostic preview.

    This command does not calculate or display the canonical evidence-backed
    SignalEngine score or canonical signal_authority_coverage.

    Use --coverage to see DB-level usable row counts per factor across all tickers.

    Examples:
        saham analyze signal-audit BBCA
        saham analyze signal-audit BBCA --date 2026-07-01
        saham analyze signal-audit BBCA --coverage
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    if date_str:
        try:
            snapshot_date = date.fromisoformat(date_str)
        except ValueError:
            typer.echo(f"[error] Invalid date: {date_str} (expected YYYY-MM-DD)", err=True)
            raise typer.Exit(1)
    else:
        snapshot_date = date.today()

    ticker_u = ticker.upper()

    try:
        engine = create_signal_engine(resolved_db, with_enrichment=True)
        ctx = engine.build_context(ticker_u, as_of_date=snapshot_date)
        active_weights, raw_weights, signal_config = resolve_signal_weight_tables(
            load_signal_engine_config_raw()
        )

        response = AuditSignalUseCase().execute(
            AuditSignalRequest(
                ticker=ticker_u,
                signal_context=ctx,
                weights=active_weights,
                raw_weights=raw_weights,
                config=signal_config,
            )
        )
    except FileNotFoundError:
        typer.echo(f"[error] Database not found at {resolved_db}.", err=True)
        typer.echo(f"        Fix:   saham fetch market {ticker_u} --days 365", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"[error] Failed to audit signal: {e}", err=True)
        raise typer.Exit(1)

    _display_report(response.report)

    if coverage:
        try:
            cov = SqliteSignalCoverageProvider().compute(resolved_db)
            _display_coverage(cov)
        except Exception as e:
            typer.echo(f"\n[warning] Coverage unavailable: {e}", err=True)


def _display_report(report: SignalAuditReport) -> None:
    typer.echo(f"\nArchived Signal Baseline Audit  ·  {report.ticker}  ·  {report.snapshot_date}")
    typer.echo("═" * 58)
    typer.echo("")
    typer.echo(
        f"{'Factor':<18}{'Status':<8}{'Raw Value':<24}{'Score':>6}  {'Wt':>6}  {'WtdContrib':>10}"
    )
    typer.echo("─" * 74)

    for e in report.entries:
        label = _FACTOR_LABELS.get(e.factor, e.factor)[:17]
        status = "✓" if e.present else "✗"
        raw = e.raw_value[:23]
        wt_pct = f"{e.active_weight * 100:.1f}%"
        suffix = "" if e.present else "  (neutral fill)"
        typer.echo(
            f"{label:<18}{status:<8}{raw:<24}"
            f"{e.component_score:>6.1f}  {wt_pct:>6}  {e.weighted_contribution:>10.1f}{suffix}"
        )

    typer.echo("─" * 74)
    typer.echo(
        f"ARCHIVED BASELINE SCORE: {report.final_score}/100  {report.strength}  {report.entry_quality}"
    )
    typer.echo("")
    typer.echo(
        f"Legacy flat-factor renormalized (missing excluded): {report.renormalized_score}/100"
    )
    typer.echo("")
    typer.echo("Note: This command audits the archived six-factor baseline and does not")
    typer.echo("      display canonical production authority coverage.")
    typer.echo("")
    total = report.factors_present + report.factors_missing
    typer.echo(f"Archived factor presence: {report.factors_present}/{total}")
    if report.coverage_warning:
        typer.echo(f"[warning] {report.coverage_warning}", err=True)


def _display_coverage(report: SignalCoverageReport) -> None:
    typer.echo("")
    typer.echo(f"DB Factor Coverage  ·  {report.db_path}  ·  {report.as_of}")
    typer.echo("═" * 58)
    typer.echo(f"Total tickers in DB (candles): {report.total_tickers_in_db}")
    typer.echo("")
    typer.echo(f"{'Factor':<22}{'Rows':>8}{'Usable':>9}{'Tickers':>9}  {'Note'}")
    typer.echo("─" * 70)
    for f in report.factors:
        note = f.note or "directional quality filter applied"
        typer.echo(f"{f.factor:<22}{f.total_rows:>8}{f.usable_rows:>9}{f.total_tickers:>9}  {note}")
    typer.echo("─" * 70)
