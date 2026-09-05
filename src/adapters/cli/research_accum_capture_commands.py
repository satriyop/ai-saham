"""
CLI: saham research signal capture

Session-scoped authoritative observation capture for accumulation-discovery.v2.
Writes learning_observations; does not generate forward labels.

Layer: Adapter (parse, wire, format, map errors).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.cli_errors import raise_data_unavailable
from src.adapters.cli.research_accum_backfill_commands import (
    _display_backfill_response,
    run_signal_observation_corpus_write,
)
from src.application.services.accum_session_capture_outcome import (
    AccumSessionCaptureStatus,
    classify_accum_session_capture,
    missing_ihsg_sessions,
)
from src.application.use_case.backfill_signal_observations_use_case import (
    BackfillSignalObservationsResponse,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractError,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    LearningArtifactReadIntegrityError,
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def _parse_session_date(raw: str, *, flag: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        typer.echo(f"[error] Invalid {flag}; expected YYYY-MM-DD", err=True)
        raise typer.Exit(1)


def _ihsg_has_session(resolved_db: Path, session_date: date) -> bool:
    candles = SQLiteMarketRepository(resolved_db).get_candles(
        "IHSG",
        start_date=session_date,
        end_date=session_date,
    )
    return any(candle.date == session_date for candle in candles)


def _ihsg_dates(resolved_db: Path, start_date: date, end_date: date) -> tuple[date, ...]:
    candles = SQLiteMarketRepository(resolved_db).get_candles(
        "IHSG",
        start_date=start_date,
        end_date=end_date,
    )
    return tuple(sorted({candle.date for candle in candles}))


def _same_day_auction_evidence(resolved_db: Path, session_date: date) -> bool:
    return SQLiteIEVRepository(resolved_db).count_snapshot_rows(session_date) > 0


def _captured_accum_sessions(resolved_db: Path) -> frozenset[date]:
    observations = SQLiteLearningArtifactRepository(resolved_db).list_observations(
        AssessmentPurpose.ACCUMULATION_DISCOVERY
    )
    return frozenset(
        observation.cutoff_at.astimezone(IDX_TIMEZONE).date() for observation in observations
    )


def _enforce_session_capture_outcome(
    *,
    session_date: date,
    processed_dates: tuple[date, ...],
    resolved_db: Path,
) -> None:
    outcome = classify_accum_session_capture(
        session=session_date,
        processed_dates=processed_dates,
        ihsg_has_session=_ihsg_has_session(resolved_db, session_date),
        same_day_auction_evidence=_same_day_auction_evidence(resolved_db, session_date),
    )
    typer.echo(
        f"[session-gate] {session_date.isoformat()} status={outcome.status.value} "
        f"ok={str(outcome.ok).lower()} {outcome.reason}",
        err=True,
    )
    if outcome.ok:
        return
    if outcome.status is AccumSessionCaptureStatus.EOD_DATA_MISSING:
        raise_data_unavailable(
            outcome.reason,
            tip=(
                "Retry `saham fetch market --universe lq45 --candles-only` after "
                "Stockbit publishes EOD, then re-run capture."
            ),
        )
    raise_data_unavailable(
        outcome.reason,
        tip="Re-run `saham research accum catch-up` after market data is present.",
    )


def signal_capture_observations(
    universe: Annotated[
        str,
        typer.Option("--universe", "-u", help="Universe name, e.g. lq45"),
    ],
    session: Annotated[
        str,
        typer.Option(
            "--session",
            help="Trading session date YYYY-MM-DD (single-day capture)",
        ),
    ],
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    require_session: Annotated[
        bool,
        typer.Option(
            "--require-session/--allow-empty-session",
            help=(
                "Fail closed when this session traded but capture processed "
                "nothing. Holiday (no IHSG, no IEV) remains success."
            ),
        ),
    ] = True,
) -> None:
    """Capture canonical accumulation learning observations for one session.

    Writes database-owned ADR-056 session observations. Labels are a separate step.
    Membership is point-in-time tradable (``{universe}@pit``), same as backfill.
    Default ``--require-session`` refuses COMPLETION_OK-style success when the
    session traded and nothing was persisted.
    """
    session_date = _parse_session_date(session, flag="--session")

    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    try:
        already_captured = session_date in _captured_accum_sessions(resolved_db)
    except (LearningContractError, LearningArtifactReadIntegrityError, OSError):
        already_captured = False
    if already_captured:
        response = BackfillSignalObservationsResponse(
            requested_date_count=1,
            processed_date_count=1,
            skipped_date_count=0,
            saved_observation_count=0,
            generated_label_count=0,
            unavailable_label_count=0,
            processed_dates=(session_date,),
            notes=("session_already_captured",),
        )
    else:
        response = run_signal_observation_corpus_write(
            universe=universe,
            start_date=session_date,
            end_date=session_date,
            resolved_db=resolved_db,
        )

    if require_session:
        _enforce_session_capture_outcome(
            session_date=session_date,
            processed_dates=response.processed_dates,
            resolved_db=resolved_db,
        )

    if fmt == "json":
        typer.echo(json.dumps(response.to_dict(), indent=2))
        return
    _display_backfill_response(response, title="Signal Observation Capture")


def signal_catch_up_observations(
    universe: Annotated[
        str,
        typer.Option("--universe", "-u", help="Universe name, e.g. lq45"),
    ],
    end: Annotated[
        str,
        typer.Option("--end", help="End session YYYY-MM-DD (inclusive)"),
    ],
    lookback_days: Annotated[
        int,
        typer.Option(
            "--lookback-days",
            help="Calendar days of IHSG history to inspect for holes",
        ),
    ] = 14,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Fill accumulation observation holes for local IHSG sessions.

    Replays only dates that have an IHSG candle and zero accum observations.
    Already-captured sessions are left unchanged. Does not rewrite rows.
    """
    if lookback_days < 1:
        typer.echo("[error] --lookback-days must be >= 1", err=True)
        raise typer.Exit(1)
    end_date = _parse_session_date(end, flag="--end")
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    start_date = end_date - timedelta(days=lookback_days)
    missing = missing_ihsg_sessions(
        ihsg_dates=_ihsg_dates(resolved_db, start_date, end_date),
        captured_sessions=_captured_accum_sessions(resolved_db),
    )
    typer.echo(
        f"[catch-up] window={start_date.isoformat()}..{end_date.isoformat()} "
        f"missing={','.join(day.isoformat() for day in missing) or 'none'}",
        err=True,
    )
    saved = 0
    processed: list[date] = []
    for session_date in missing:
        response = run_signal_observation_corpus_write(
            universe=universe,
            start_date=session_date,
            end_date=session_date,
            resolved_db=resolved_db,
        )
        saved += response.saved_observation_count
        processed.extend(response.processed_dates)
        typer.echo(
            f"[catch-up] {session_date.isoformat()} "
            f"saved={response.saved_observation_count} "
            f"processed={response.processed_date_count}",
            err=True,
        )
        _enforce_session_capture_outcome(
            session_date=session_date,
            processed_dates=response.processed_dates,
            resolved_db=resolved_db,
        )

    payload = {
        "artifact_type": "accumulation_observation_catch_up",
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "missing_sessions": [day.isoformat() for day in missing],
        "processed_dates": [day.isoformat() for day in processed],
        "saved_observation_count": saved,
    }
    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo("Signal Observation Catch-up")
    typer.echo("═" * 72)
    typer.echo(f"Window: {start_date.isoformat()} → {end_date.isoformat()}")
    typer.echo(f"Missing sessions: {len(missing)}")
    typer.echo(f"Processed dates: {len(processed)}")
    typer.echo(f"Saved observation rows: {saved}")
