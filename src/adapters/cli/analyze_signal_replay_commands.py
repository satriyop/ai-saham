"""
CLI: retrieve a stored signal observation (DQ-005 Slice A — retrieval-only).

Does not recompute. Does not claim replay reproducibility.
Layer: Adapter (parse, wire, format, map errors).
"""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.retrieve_stored_signal_observation_use_case import (
    ObservationSelectionStatus,
    RetrieveStoredSignalObservationRequest,
    RetrieveStoredSignalObservationUseCase,
    StoredObservationIdentity,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)


def signal_replay(
    ticker: Annotated[str, typer.Argument(help="IDX ticker (e.g. BBCA)")],
    snapshot_date: Annotated[str, typer.Argument(help="Snapshot date YYYY-MM-DD")],
    captured_at: Annotated[
        Optional[str],
        typer.Option(
            "--captured-at",
            help=(
                "Exact observation_captured_at (ISO datetime). Required when "
                "multiple stored versions exist for ticker/date."
            ),
        ),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Retrieve a stored signal observation (retrieval-only; does not recompute).

    Command name remains ``signal-replay`` until CLI restructure; behavior is
    explicitly retrieval-only per DQ-005 Slice A.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    ticker_u = ticker.upper()
    try:
        day = date.fromisoformat(snapshot_date)
    except ValueError:
        typer.echo(f"[error] Invalid date: {snapshot_date} (expected YYYY-MM-DD)", err=True)
        raise typer.Exit(1)

    parsed_captured_at: datetime | None = None
    if captured_at is not None:
        try:
            parsed_captured_at = datetime.fromisoformat(captured_at)
        except ValueError:
            typer.echo(
                f"[error] Invalid --captured-at: {captured_at} "
                "(expected ISO datetime, e.g. 2026-07-03T09:00:00)",
                err=True,
            )
            raise typer.Exit(1)

    try:
        repo = SQLiteCandidateObservationsRepository(resolved_db)
        response = RetrieveStoredSignalObservationUseCase(repo).execute(
            RetrieveStoredSignalObservationRequest(
                ticker=ticker_u,
                snapshot_date=day,
                observation_captured_at=parsed_captured_at,
            )
        )
    except Exception as exc:
        typer.echo(f"[error] Failed to retrieve stored signal observation: {exc}", err=True)
        raise typer.Exit(1)

    if response.status is ObservationSelectionStatus.NOT_FOUND:
        typer.echo(
            f"[error] No stored signal observation for {ticker_u} on {day}"
            + (
                f" at captured_at={parsed_captured_at.isoformat()}"
                if parsed_captured_at is not None
                else ""
            )
            + ".",
            err=True,
        )
        typer.echo(
            "        Capture first via signal observation backfill "
            "(or screen accum), then retrieve by identity.",
            err=True,
        )
        raise typer.Exit(1)

    if response.status is ObservationSelectionStatus.AMBIGUOUS:
        typer.echo(
            f"[error] Multiple stored observation versions for {ticker_u} on {day}.",
            err=True,
        )
        typer.echo(
            "        Retrieval is not silent latest-pick. Pass --captured-at "
            "with one of:",
            err=True,
        )
        for identity in response.candidates:
            typer.echo(f"          {_format_identity_line(identity)}", err=True)
        raise typer.Exit(1)

    assert response.observation is not None
    assert response.selected_identity is not None
    _display_retrieval(response.observation.payload, response.selected_identity)


def _format_identity_line(identity: StoredObservationIdentity) -> str:
    data_as_of = (
        identity.data_as_of_date.isoformat()
        if identity.data_as_of_date is not None
        else "—"
    )
    return (
        f"captured_at={identity.captured_at.isoformat()} "
        f"window_sessions={identity.window_sessions} "
        f"config_hash={identity.config_hash or '—'} "
        f"schema={identity.schema_version if identity.schema_version is not None else '—'} "
        f"data_as_of={data_as_of}"
    )


def _display_retrieval(payload: dict, identity: StoredObservationIdentity) -> None:
    ticker = identity.ticker
    snapshot_date = identity.snapshot_date.isoformat()
    signal = payload.get("signal") or {}
    assessment = signal.get("assessment") or {}
    candidate = payload.get("candidate") or {}
    trade_setup = payload.get("trade_setup") or {}

    typer.echo(f"\nStored Observation (retrieval-only)  ·  {ticker}  ·  {snapshot_date}")
    typer.echo("═" * 58)
    typer.echo("Mode:     RETRIEVAL_ONLY (does not recompute; not a reproducibility proof)")
    typer.echo(f"Identity: {_format_identity_line(identity)}")
    typer.echo(f"Workflow: {identity.workflow}")
    if identity.observation_contract:
        typer.echo(f"Contract: {identity.observation_contract}")
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
