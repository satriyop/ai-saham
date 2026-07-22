"""
CLI: retrieve or verify a stored signal observation (DQ-005).

Default: Slice A retrieval-only.
``--verify``: Slice B lean local recompute + MATCH/DRIFT/UNREPRODUCIBLE.

Layer: Adapter (parse, wire, format, map errors). No cutoff/cohort/compare policy.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.analyze_signal_backfill_commands import (
    _read_scoring_config_canonical,
)
from src.adapters.cli.screen_accum_workflow_factory import (
    create_accumulation_screen_workflow_bundle,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.lean_observation_identity import (
    resolve_lean_semantic_compatibility_id,
)
from src.application.services.signal_observation_request_builder import (
    BuildSignalObservationScreenRequest,
)
from src.application.use_case.retrieve_stored_signal_observation_use_case import (
    ObservationSelectionStatus,
    RetrieveStoredSignalObservationRequest,
    RetrieveStoredSignalObservationUseCase,
    StoredObservationIdentity,
)
from src.application.use_case.verify_stored_signal_observation_use_case import (
    ObservationVerifyStatus,
    VerifyStoredSignalObservationRequest,
    VerifyStoredSignalObservationUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.swing_config_loader import load_swing_config
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


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
    verify: Annotated[
        bool,
        typer.Option(
            "--verify",
            help=(
                "DQ-005 Slice B: re-screen locally at the recorded cutoff and "
                "compare score/coverage/setup_phase/fingerprint_digest. "
                "Does not refetch remote providers; does not persist."
            ),
        ),
    ] = False,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Retrieve a stored observation, or verify it via local recompute.

    Public path: ``saham research signal replay``.
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

    if verify:
        _run_verify(
            ticker=ticker_u,
            snapshot_date=day,
            captured_at=parsed_captured_at,
            db_path=resolved_db,
            config_paths=cfg.config_paths,
        )
        return

    _run_retrieve(
        ticker=ticker_u,
        snapshot_date=day,
        captured_at=parsed_captured_at,
        db_path=resolved_db,
    )


def _run_retrieve(
    *,
    ticker: str,
    snapshot_date: date,
    captured_at: datetime | None,
    db_path: Path,
) -> None:
    try:
        repo = SQLiteCandidateObservationsRepository(db_path)
        response = RetrieveStoredSignalObservationUseCase(repo).execute(
            RetrieveStoredSignalObservationRequest(
                ticker=ticker,
                snapshot_date=snapshot_date,
                observation_captured_at=captured_at,
            )
        )
    except Exception as exc:
        typer.echo(f"[error] Failed to retrieve stored signal observation: {exc}", err=True)
        raise typer.Exit(1)

    if response.status is ObservationSelectionStatus.NOT_FOUND:
        typer.echo(
            f"[error] No stored signal observation for {ticker} on {snapshot_date}"
            + (
                f" at captured_at={captured_at.isoformat()}"
                if captured_at is not None
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
            f"[error] Multiple stored observation versions for {ticker} on {snapshot_date}.",
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


def _run_verify(
    *,
    ticker: str,
    snapshot_date: date,
    captured_at: datetime | None,
    db_path: Path,
    config_paths,
) -> None:
    try:
        observations_repo = SQLiteCandidateObservationsRepository(db_path)
        market_repo = SQLiteMarketRepository(db_path)
        accumulation_config = load_accumulation_screener_config()
        swing_config = load_swing_config()
        screen_bundle = create_accumulation_screen_workflow_bundle(
            db_path=db_path,
            screener_config=accumulation_config,
            swing_config=swing_config,
        )
        screen_request_builder = BuildSignalObservationScreenRequest.from_configs(
            swing_config=swing_config,
            accumulation_screener_config=accumulation_config,
            min_net_buy_days=1,
            disable_score_filters=True,
        )
        current_cohort_id = resolve_lean_semantic_compatibility_id(
            _read_scoring_config_canonical(config_paths)
        )
        response = VerifyStoredSignalObservationUseCase(
            observations_repository=observations_repo,
            screen_use_case=screen_bundle.screen_use_case,
            screen_request_builder=screen_request_builder,
            session_resolver=EffectiveMarketSessionResolver(market_repo),
            current_semantic_compatibility_id=current_cohort_id,
            candidate_evidence_builder=screen_bundle.candidate_evidence_builder,
        ).execute(
            VerifyStoredSignalObservationRequest(
                ticker=ticker,
                snapshot_date=snapshot_date,
                observation_captured_at=captured_at,
            )
        )
    except Exception as exc:
        typer.echo(f"[error] Failed to verify stored signal observation: {exc}", err=True)
        raise typer.Exit(1)

    _display_verify(response)

    if response.status is ObservationVerifyStatus.AMBIGUOUS:
        raise typer.Exit(1)
    if response.status is ObservationVerifyStatus.UNREPRODUCIBLE:
        raise typer.Exit(2)
    if response.status is ObservationVerifyStatus.DRIFT:
        raise typer.Exit(3)


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


def _display_verify(response) -> None:
    typer.echo("\nStored Observation Verify (local recompute)")
    typer.echo("═" * 58)
    typer.echo("Mode:     VERIFY_LOCAL_RECOMPUTE (no network refetch; not promotion-grade)")
    if response.selected_identity is not None:
        typer.echo(f"Identity: {_format_identity_line(response.selected_identity)}")
    typer.echo(f"Status:   {response.status.value}")
    if response.reasons:
        typer.echo("Reasons:")
        for reason in response.reasons:
            typer.echo(f"  - {reason}")
    if response.status is ObservationVerifyStatus.AMBIGUOUS:
        typer.echo("Candidates (pass --captured-at):")
        for identity in response.candidates:
            typer.echo(f"  - {_format_identity_line(identity)}")
    if response.differences:
        typer.echo("Differences:")
        for diff in response.differences:
            typer.echo(
                f"  - {diff.field}: stored={diff.stored!r} recomputed={diff.recomputed!r}"
            )
    for note in response.notes:
        typer.echo(f"Note:     {note}")
