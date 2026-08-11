"""
`saham audit corpus-continuity` — report sessions missing from a learning corpus.

Adapter only: parses flags, wires repositories, calls the continuity use case,
renders the result, and maps health onto an exit code. It owns no continuity
policy — what counts as a hole, what width is expected, and how far back an
unrepaired hole keeps alarming all live in
``AuditCorpusContinuityUseCase``.

Layer: Adapter (CLI)
AI usage: None
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from src.adapters.cli.cli_errors import (
    EXIT_DATA,
    echo_cli_empty,
    resolve_cli_db_path,
)
from src.application.dto.corpus_continuity import (
    CorpusContinuityRequest,
    CorpusContinuityResponse,
    SessionContinuityStatus,
)
from src.application.use_case.audit_corpus_continuity_use_case import (
    AuditCorpusContinuityUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_trading_session_calendar_snapshot_repository import (
    SQLiteTradingSessionCalendarSnapshotReadRepository,
)

_VALID_FORMATS = ("table", "json")

_PURPOSE_BY_ALIAS: dict[str, AssessmentPurpose] = {
    "accum": AssessmentPurpose.ACCUMULATION_DISCOVERY,
    "pre-open": AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
    "swing": AssessmentPurpose.SWING_TRADE_SETUP,
}

_STATUS_STYLE: dict[SessionContinuityStatus, str] = {
    SessionContinuityStatus.OK: "green",
    SessionContinuityStatus.MISSING: "bold red",
    SessionContinuityStatus.UNDER_COVERED: "yellow",
    SessionContinuityStatus.NO_CALENDAR_AUTHORITY: "dim",
}


def corpus_continuity(
    purpose: Annotated[
        str,
        typer.Option(
            "--purpose",
            help=f"Corpus to audit: {', '.join(_PURPOSE_BY_ALIAS)}.",
        ),
    ] = "accum",
    compatibility_id: Annotated[
        Optional[str],
        typer.Option("--compatibility-id", help="Restrict to one cohort identity."),
    ] = None,
    expected_width: Annotated[
        Optional[int],
        typer.Option(
            "--expected-width",
            help=(
                "Declared per-session observation count (e.g. 45 for LQ45). "
                "Thin sessions are flagged only when this is given."
            ),
        ),
    ] = None,
    min_coverage_fraction: Annotated[
        float,
        typer.Option(
            "--min-coverage",
            help="Share of --expected-width a session must reach to count as complete.",
        ),
    ] = 0.9,
    lookback_sessions: Annotated[
        Optional[int],
        typer.Option(
            "--lookback",
            help=(
                "Only the N most recent sessions affect health, so a known "
                "unrepairable old hole stops re-alerting. Omit to require the "
                "whole window clean."
            ),
        ),
    ] = None,
    window_start: Annotated[
        Optional[str],
        typer.Option("--start", help="Window start YYYY-MM-DD. Defaults to first capture."),
    ] = None,
    as_of: Annotated[
        Optional[str],
        typer.Option("--as-of", help="Window end YYYY-MM-DD. Defaults to today (WIB)."),
    ] = None,
    require_healthy: Annotated[
        bool,
        typer.Option(
            "--require-healthy",
            help="Exit 2 when the corpus has a hole. Use this in cron.",
        ),
    ] = False,
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
    Report which trading sessions a learning corpus is missing.

    Compares captured observations against the attested trading-session
    calendar, so a capture that silently failed becomes visible the next day
    instead of months later.
    """
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    resolved_purpose = _PURPOSE_BY_ALIAS.get(purpose)
    if resolved_purpose is None:
        raise typer.BadParameter(
            f"--purpose must be one of {tuple(_PURPOSE_BY_ALIAS)}, got '{purpose}'."
        )
    if not 0 < min_coverage_fraction <= 1:
        raise typer.BadParameter("--min-coverage must be within (0, 1].")
    if expected_width is not None and expected_width <= 0:
        raise typer.BadParameter("--expected-width must be positive.")
    if lookback_sessions is not None and lookback_sessions <= 0:
        raise typer.BadParameter("--lookback must be positive.")

    request = CorpusContinuityRequest(
        purpose=resolved_purpose,
        as_of=_parse_date(as_of, "--as-of") or _today_wib(),
        compatibility_id=compatibility_id,
        window_start=_parse_date(window_start, "--start"),
        expected_observation_count=expected_width,
        alert_lookback_sessions=lookback_sessions,
        min_coverage_fraction=min_coverage_fraction,
    )
    _run(request=request, db_path=db_path, output_format=output_format, strict=require_healthy)


def _run(
    *,
    request: CorpusContinuityRequest,
    db_path: Path | None,
    output_format: str,
    strict: bool,
) -> None:
    cfg = load_app_config()
    resolved_db = resolve_cli_db_path(db_path, configured_default=cfg.storage.db_path)

    use_case = AuditCorpusContinuityUseCase(
        observations=SQLiteLearningArtifactRepository(resolved_db),
        calendar_snapshots=SQLiteTradingSessionCalendarSnapshotReadRepository(resolved_db),
    )
    response = use_case.execute(request)

    if output_format == "json":
        typer.echo(json.dumps(_to_dict(response), indent=2, ensure_ascii=False))
    elif not response.rows:
        echo_cli_empty(
            f"No {request.purpose.value} observations to audit.",
            next_step="saham research accum capture --universe lq45",
        )
    else:
        _print_table(response)

    if strict and not response.operationally_healthy:
        raise typer.Exit(code=EXIT_DATA)


def _print_table(response: CorpusContinuityResponse) -> None:
    console = Console()
    counts = response.counts()

    table = Table(
        title=(
            f"Corpus continuity — {response.purpose.value}  "
            f"{response.window_start} → {response.window_end}"
        ),
        header_style="bold",
    )
    table.add_column("Session")
    table.add_column("Status")
    table.add_column("Observations", justify="right")

    for row in response.rows:
        if row.status is SessionContinuityStatus.OK:
            continue
        expected = (
            f" / {row.expected_observation_count}"
            if row.expected_observation_count is not None
            else ""
        )
        table.add_row(
            row.session_date.isoformat(),
            f"[{_STATUS_STYLE[row.status]}]{row.status.value}[/]",
            f"{row.observation_count}{expected}",
        )

    if table.row_count:
        console.print(table)
    else:
        console.print(
            f"[green]All {counts[SessionContinuityStatus.OK.value]} sessions captured[/] "
            f"({response.window_start} → {response.window_end})"
        )

    summary = "  ".join(f"{status}={count}" for status, count in counts.items() if count)
    console.print(f"  {summary}")
    if response.observed_modal_width is not None:
        console.print(f"  modal width: {response.observed_modal_width}")
    console.print(f"  calendar snapshots: {len(response.calendar_snapshot_ids)}")
    verdict = "HEALTHY" if response.operationally_healthy else "HOLE DETECTED"
    style = "green" if response.operationally_healthy else "bold red"
    horizon = (
        f" (last {response.alert_lookback_sessions} sessions)"
        if response.alert_lookback_sessions is not None
        else ""
    )
    console.print(f"  [{style}]{verdict}[/]{horizon}")


def _to_dict(response: CorpusContinuityResponse) -> dict:
    return {
        "purpose": response.purpose.value,
        "compatibility_id": response.compatibility_id,
        "window_start": response.window_start.isoformat() if response.window_start else None,
        "window_end": response.window_end.isoformat(),
        "expected_observation_count": response.expected_observation_count,
        "observed_modal_width": response.observed_modal_width,
        "alert_lookback_sessions": response.alert_lookback_sessions,
        "calendar_snapshot_ids": list(response.calendar_snapshot_ids),
        "counts": response.counts(),
        "operationally_healthy": response.operationally_healthy,
        "missing_sessions": [day.isoformat() for day in response.missing_sessions],
        "under_covered_sessions": [day.isoformat() for day in response.under_covered_sessions],
        "unattestable_sessions": [day.isoformat() for day in response.unattestable_sessions],
        "sessions": [
            {
                "session_date": row.session_date.isoformat(),
                "status": row.status.value,
                "observation_count": row.observation_count,
                "expected_observation_count": row.expected_observation_count,
            }
            for row in response.rows
        ],
    }


def _parse_date(raw: str | None, flag: str) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(f"{flag} must be YYYY-MM-DD, got '{raw}'.") from exc


def _today_wib() -> date:
    from datetime import datetime

    return datetime.now(IDX_TIMEZONE).date()
