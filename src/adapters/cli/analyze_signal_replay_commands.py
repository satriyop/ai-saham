"""
CLI commands for SignalEngine replay.

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.replay_signal_observation_use_case import (
    ReplaySignalObservationRequest,
    ReplaySignalObservationUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)


def signal_replay(
    ticker: Annotated[str, typer.Argument(help="IDX ticker (e.g. BBCA)")],
    snapshot_date: Annotated[str, typer.Argument(help="Snapshot date YYYY-MM-DD")],
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Replay the latest stored signal observation for ticker/date."""
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
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
    # HIGH-2 canonical field; legacy schema 1/2 payloads persisted before the
    # schema-3 rename only have the old ambiguous keys — read them here only
    # as an explicit legacy diagnostic fallback for display, never remapped
    # into canonical signal_authority_coverage semantics elsewhere.
    coverage = assessment.get("signal_authority_coverage")
    if coverage is None:
        coverage = assessment.get("coverage_score") or assessment.get("confidence_score")
    coverage_text = "—" if coverage is None else f"{float(coverage):.0%}"
    typer.echo(
        "Signal:  "
        f"{assessment.get('score', '—')}/100  "
        f"{assessment.get('strength', '—')}  "
        f"{assessment.get('entry_quality', '—')}  "
        f"cov={coverage_text}"
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
