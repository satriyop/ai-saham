"""
CLI implementation for `saham analyze signal-audit`.

Phase 0 observability command for the SignalEngine composite score. Shows the
exact per-factor inputs feeding the current flat-weighted score for one ticker:
presence, raw context value, component score, configured/active weight, and
weighted contribution. Also shows the legacy flat-factor renormalized score
(missing factors excluded from the weight pool) for diagnostic reference.

Adapter responsibilities only: parse input, wire dependencies, call use cases,
format output. No scoring policy lives here.

Layer: Adapter
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.services.bootstrap import (
    create_signal_engine,
    load_signal_weight_tables,
)
from src.application.ports.signal_coverage_provider import SignalCoverageReport
from src.infrastructure.persistence.sqlite_signal_coverage_provider import (
    SqliteSignalCoverageProvider,
)
from src.application.use_case.audit_signal_use_case import (
    AuditSignalRequest,
    AuditSignalUseCase,
)
from src.application.use_case.replay_signal_observation_use_case import (
    ReplaySignalObservationRequest,
    ReplaySignalObservationUseCase,
)
from src.domain.value_objects.signal_audit import SignalAuditReport
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)

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
    Audit current SignalEngine inputs for one ticker — factor presence, scores, weights.

    Shows per-factor: present/missing, raw context value, component score (0-100),
    configured weight, active weight, weighted contribution, and composite total.

    Also shows the legacy flat-factor renormalized score (missing factors excluded
    from the weight pool) for diagnostic reference alongside the canonical score.

    Use --coverage to see DB-level usable row counts per factor across all tickers.

    Examples:
        saham analyze signal-audit BBCA
        saham analyze signal-audit BBCA --date 2026-07-01
        saham analyze signal-audit BBCA --coverage
    """
    resolved_db = db_path or DEFAULT_DB_PATH

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
        active_weights, raw_weights, signal_config = load_signal_weight_tables()

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


def signal_replay(
    ticker: Annotated[str, typer.Argument(help="IDX ticker (e.g. BBCA)")],
    snapshot_date: Annotated[str, typer.Argument(help="Snapshot date YYYY-MM-DD")],
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Replay the latest stored signal observation for ticker/date."""
    resolved_db = db_path or DEFAULT_DB_PATH
    ticker_u = ticker.upper()
    try:
        day = date.fromisoformat(snapshot_date)
    except ValueError:
        typer.echo(f"[error] Invalid date: {snapshot_date} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)

    try:
        repo = SQLiteCandidateObservationsRepository(resolved_db)
        response = ReplaySignalObservationUseCase(repo).execute(
            ReplaySignalObservationRequest(ticker=ticker_u, snapshot_date=day)
        )
    except Exception as exc:
        typer.echo(f"[error] Failed to replay signal observation: {exc}", err=True)
        raise typer.Exit(1)

    if response.observation is None:
        typer.echo(f"[error] No stored signal observation for {ticker_u} on {day}.", err=True)
        typer.echo("        Run: saham screen accum to capture observations first.", err=True)
        raise typer.Exit(1)

    _display_replay(response.observation.payload)


# ── display ───────────────────────────────────────────────────────────────────

def _display_report(report: SignalAuditReport) -> None:
    typer.echo(
        f"\nSignal Audit  ·  {report.ticker}  ·  {report.snapshot_date}"
    )
    typer.echo("═" * 58)
    typer.echo("")
    typer.echo(
        f"{'Factor':<18}{'Status':<8}{'Raw Value':<24}"
        f"{'Score':>6}  {'Wt':>6}  {'WtdContrib':>10}"
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
        f"COMPOSITE SCORE: {report.final_score}/100  "
        f"{report.strength}  {report.entry_quality}"
    )
    typer.echo("")
    typer.echo(
        f"Legacy flat-factor renormalized (missing excluded): "
        f"{report.renormalized_score}/100"
    )
    typer.echo("")
    total = report.factors_present + report.factors_missing
    typer.echo(f"Coverage: {report.factors_present}/{total} factors present")
    if report.coverage_warning:
        typer.echo(f"[warning] {report.coverage_warning}", err=True)


def _display_replay(payload: dict) -> None:
    ticker = payload.get("ticker", "?")
    snapshot_date = payload.get("snapshot_date", "?")
    captured_at = payload.get("captured_at", "?")
    signal = payload.get("signal") or {}
    assessment = signal.get("assessment") or {}
    candidate = payload.get("candidate") or {}
    trade_setup = payload.get("trade_setup") or {}

    typer.echo(f"\nSignal Replay  ·  {ticker}  ·  {snapshot_date}")
    typer.echo("═" * 58)
    typer.echo(f"Captured: {captured_at}")
    typer.echo(f"Schema:   {payload.get('schema_version', '?')}")
    typer.echo("")
    confidence = assessment.get("confidence_score")
    confidence_text = "—" if confidence is None else f"{float(confidence):.0%}"
    typer.echo(
        "Signal:  "
        f"{assessment.get('score', '—')}/100  "
        f"{assessment.get('strength', '—')}  "
        f"{assessment.get('entry_quality', '—')}  "
        f"conf={confidence_text}"
    )
    if signal.get("coverage_warning"):
        typer.echo(f"Warning: {signal['coverage_warning']}")
    typer.echo(
        "Flow:    "
        f"{candidate.get('foreign_flow_score', '—')}  "
        f"trend={candidate.get('trend', '—')}  "
        f"streak={candidate.get('consecutive_streak', '—')}"
    )
    if trade_setup:
        typer.echo(
            "Action:  "
            f"{trade_setup.get('action', '—')}  "
            f"risk={trade_setup.get('risk_level', '—')}"
        )
    breakdown = assessment.get("breakdown") or {}
    if breakdown:
        typer.echo("")
        typer.echo("Breakdown:")
        for key, value in breakdown.items():
            typer.echo(f"  {key}: {value}")


def _display_coverage(report: SignalCoverageReport) -> None:
    typer.echo("")
    typer.echo(f"DB Factor Coverage  ·  {report.db_path}  ·  {report.as_of}")
    typer.echo("═" * 58)
    typer.echo(f"Total tickers in DB (candles): {report.total_tickers_in_db}")
    typer.echo("")
    typer.echo(
        f"{'Factor':<22}{'Rows':>8}{'Usable':>9}{'Tickers':>9}  {'Note'}"
    )
    typer.echo("─" * 70)
    for f in report.factors:
        note = f.note or "directional quality filter applied"
        typer.echo(
            f"{f.factor:<22}{f.total_rows:>8}{f.usable_rows:>9}{f.total_tickers:>9}  {note}"
        )
    typer.echo("─" * 70)
