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

import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.ports.signal_coverage_provider import SignalCoverageReport
from src.application.services.bootstrap import (
    create_signal_engine,
    load_signal_weight_tables,
)
from src.application.use_case.audit_signal_use_case import (
    AuditSignalRequest,
    AuditSignalUseCase,
)
from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateSignalForwardLabelsRequest,
    GenerateSignalForwardLabelsUseCase,
)
from src.application.use_case.replay_signal_observation_use_case import (
    ReplaySignalObservationRequest,
    ReplaySignalObservationUseCase,
)
from src.application.use_case.summarize_signal_forward_labels_use_case import (
    SummarizeSignalForwardLabelsRequest,
    SummarizeSignalForwardLabelsUseCase,
)
from src.domain.value_objects.signal_audit import SignalAuditReport
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_signal_coverage_provider import (
    SqliteSignalCoverageProvider,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
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


def signal_labels(
    snapshot_date: Annotated[str, typer.Argument(help="Signal date YYYY-MM-DD")],
    ticker: Annotated[
        Optional[str],
        typer.Option("--ticker", "-t", help="Limit to one ticker; required with --generate"),
    ] = None,
    horizon: Annotated[
        str,
        typer.Option("--horizon", help="TACTICAL_3D, SWING_10D, or ACCUM_20D"),
    ] = SignalLabelHorizon.SWING_10D.value,
    generate: Annotated[
        bool,
        typer.Option("--generate", help="Generate label before summarizing"),
    ] = False,
    captured_at: Annotated[
        Optional[str],
        typer.Option("--captured-at", help="Specific observation timestamp ISO-8601"),
    ] = None,
    fmt: Annotated[str, typer.Option("--format", help="Output format: table or json")] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Generate and summarize persisted signal forward labels."""
    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        day = date.fromisoformat(snapshot_date)
    except ValueError:
        typer.echo(f"[error] Invalid date: {snapshot_date} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)
    try:
        label_horizon = SignalLabelHorizon(horizon.upper())
    except ValueError:
        typer.echo(f"[error] Invalid horizon: {horizon}", err=True)
        raise typer.Exit(1)
    try:
        captured_dt = datetime.fromisoformat(captured_at) if captured_at else None
    except ValueError:
        typer.echo(f"[error] Invalid captured-at: {captured_at}", err=True)
        raise typer.Exit(1)

    ticker_u = ticker.upper() if ticker else None
    labels_repo = SQLiteSignalForwardLabelsRepository(resolved_db)

    if generate:
        if not ticker_u:
            typer.echo("[error] --ticker is required with --generate", err=True)
            raise typer.Exit(1)
        generator = GenerateSignalForwardLabelsUseCase(
            candidate_observations_repository=SQLiteCandidateObservationsRepository(resolved_db),
            market_data_repository=SQLiteMarketRepository(resolved_db),
            signal_forward_labels_repository=labels_repo,
        )
        response = generator.execute(
            GenerateSignalForwardLabelsRequest(
                ticker=ticker_u,
                signal_date=day,
                observation_captured_at=captured_dt,
                horizons=(label_horizon,),
            )
        )
        if response.observation is None:
            typer.echo(f"[error] No stored signal observation for {ticker_u} on {day}.", err=True)
            typer.echo("        Run: saham screen accum to capture observations first.", err=True)
            raise typer.Exit(1)
        if fmt != "json":
            label = response.labels[0]
            typer.echo(
                f"Generated {label.horizon.value} label for {label.ticker} "
                f"{label.signal_date}: {label.outcome_label.value}"
            )

    summary = SummarizeSignalForwardLabelsUseCase(labels_repo).execute(
        SummarizeSignalForwardLabelsRequest(
            signal_date=day,
            horizon=label_horizon,
            ticker=ticker_u,
        )
    )
    if fmt == "json":
        typer.echo(json.dumps(summary.to_dict(), indent=2))
        return
    _display_label_summary(day, label_horizon, ticker_u, summary)


# ── display ───────────────────────────────────────────────────────────────────


def _display_report(report: SignalAuditReport) -> None:
    typer.echo(f"\nSignal Audit  ·  {report.ticker}  ·  {report.snapshot_date}")
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
        f"COMPOSITE SCORE: {report.final_score}/100  {report.strength}  {report.entry_quality}"
    )
    typer.echo("")
    typer.echo(
        f"Legacy flat-factor renormalized (missing excluded): {report.renormalized_score}/100"
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
            f"Action:  {trade_setup.get('action', '—')}  risk={trade_setup.get('risk_level', '—')}"
        )
    breakdown = assessment.get("breakdown") or {}
    if breakdown:
        typer.echo("")
        typer.echo("Breakdown:")
        for key, value in breakdown.items():
            typer.echo(f"  {key}: {value}")


def _display_label_summary(day, horizon, ticker, summary) -> None:
    suffix = f" · {ticker}" if ticker else ""
    typer.echo(f"\nSignal Forward Labels · {day} · {horizon.value}{suffix}")
    typer.echo("═" * 72)
    typer.echo(f"Labels: {len(summary.labels)}")
    if not summary.buckets:
        typer.echo("No saved labels found.")
        return
    typer.echo("")
    typer.echo(
        f"{'Group':<18}{'Key':<22}{'N':>4}{'S':>4}{'F':>4}{'Ntrl':>6}"
        f"{'Unav':>6}{'AvgClose':>10}{'AvgMFE':>9}{'AvgMAE':>9}"
    )
    typer.echo("─" * 92)
    for bucket in summary.buckets:
        typer.echo(
            f"{bucket.group:<18}{bucket.key:<22}{bucket.observation_count:>4}"
            f"{bucket.success_count:>4}{bucket.failure_count:>4}"
            f"{bucket.neutral_count:>6}{bucket.unavailable_count:>6}"
            f"{_fmt_pct(bucket.average_close_return):>10}"
            f"{_fmt_pct(bucket.average_max_forward_return):>9}"
            f"{_fmt_pct(bucket.average_max_adverse_excursion):>9}"
        )


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}%"


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
