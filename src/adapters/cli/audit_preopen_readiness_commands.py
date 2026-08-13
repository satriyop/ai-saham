"""
`saham audit preopen-readiness` — is today's NCP capture still on track?

Adapter only: parses flags, wires repositories, calls the readiness use case,
renders the result, and maps the verdict onto an exit code. It owns no readiness
policy — what "still usable at the NCP window" means, how much margin is
required, when the fetch check falls due, and how a holiday differs from an
unattested date all live in ``AssessPreOpenLaneReadinessUseCase``.

Layer: Adapter (CLI)
AI usage: None
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from src.adapters.cli.cli_errors import EXIT_DATA, resolve_cli_db_path
from src.application.dto.preopen_lane_readiness import (
    PreOpenLaneReadinessRequest,
    PreOpenLaneReadinessResponse,
    PreOpenReadinessStatus,
    SessionEligibility,
)
from src.application.use_case.assess_preopen_lane_readiness_use_case import (
    AssessPreOpenLaneReadinessUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_iev_repository import SQLiteIEVRepository
from src.infrastructure.persistence.sqlite_trading_session_calendar_snapshot_repository import (
    SQLiteTradingSessionCalendarSnapshotReadRepository,
)

_VALID_FORMATS = ("table", "json")

_STATUS_STYLE: dict[PreOpenReadinessStatus, str] = {
    PreOpenReadinessStatus.OK: "green",
    PreOpenReadinessStatus.AT_RISK: "bold red",
    PreOpenReadinessStatus.NOT_DUE: "dim",
    PreOpenReadinessStatus.UNKNOWN: "yellow",
}


def preopen_readiness(
    session_date: Annotated[
        Optional[str],
        typer.Option("--session", help="Session YYYY-MM-DD. Defaults to today (WIB)."),
    ] = None,
    as_of: Annotated[
        Optional[str],
        typer.Option(
            "--as-of",
            help="Assess as of this WIB wall-clock time, HH:MM. Defaults to now.",
        ),
    ] = None,
    ncp_window_end: Annotated[
        str,
        typer.Option("--window-end", help="NCP lock window close, HH:MM WIB."),
    ] = "08:58",
    token_margin_minutes: Annotated[
        int,
        typer.Option(
            "--token-margin",
            help="Minutes past the window close the token must still cover.",
        ),
    ] = 10,
    early_fetch_due_at: Annotated[
        str,
        typer.Option(
            "--fetch-due",
            help="After this WIB time, stored IEV rows are required as live proof.",
        ),
    ] = "08:48",
    min_rows: Annotated[
        int,
        typer.Option("--min-rows", help="IEV rows required once the fetch is due."),
    ] = 1,
    require_ready: Annotated[
        bool,
        typer.Option(
            "--require-ready",
            help="Exit 2 when the lane is at risk. Use this in cron.",
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
    Check whether today's pre-open lane will still work at the NCP window.

    The 08:56-08:58 capture cannot be replayed, so this runs while there is
    still time to fix a broken session by hand — unlike the corpus continuity
    watchdog, which can only report the loss after the fact.
    """
    if output_format not in _VALID_FORMATS:
        raise typer.BadParameter(
            f"--format must be one of {_VALID_FORMATS}, got '{output_format}'."
        )
    if token_margin_minutes < 0:
        raise typer.BadParameter("--token-margin must not be negative.")
    if min_rows <= 0:
        raise typer.BadParameter("--min-rows must be positive.")

    resolved_session = _parse_date(session_date, "--session")
    request = PreOpenLaneReadinessRequest(
        as_of=_resolve_as_of(as_of, resolved_session),
        session_date=resolved_session,
        ncp_window_end=_parse_time(ncp_window_end, "--window-end"),
        token_margin_minutes=token_margin_minutes,
        early_fetch_due_at=_parse_time(early_fetch_due_at, "--fetch-due"),
        min_early_fetch_rows=min_rows,
    )
    _run(request=request, db_path=db_path, output_format=output_format, strict=require_ready)


def _run(
    *,
    request: PreOpenLaneReadinessRequest,
    db_path: Path | None,
    output_format: str,
    strict: bool,
) -> None:
    cfg = load_app_config()
    resolved_db = resolve_cli_db_path(db_path, configured_default=cfg.storage.db_path)

    use_case = AssessPreOpenLaneReadinessUseCase(
        iev_snapshots=SQLiteIEVRepository(resolved_db),
        calendar_snapshots=SQLiteTradingSessionCalendarSnapshotReadRepository(resolved_db),
        session_status=_read_session_status,
    )
    response = use_case.execute(request)

    if output_format == "json":
        typer.echo(json.dumps(_to_dict(response), indent=2, ensure_ascii=False))
    else:
        _print_table(response)

    if strict and not response.on_track:
        raise typer.Exit(code=EXIT_DATA)


def _read_session_status():
    """Deferred import: reading token health pulls in the browser stack."""
    from src.infrastructure.browser.playwright_stockbit_provider import (
        get_stockbit_session_status,
    )

    return get_stockbit_session_status()


def _print_table(response: PreOpenLaneReadinessResponse) -> None:
    console = Console()
    console.print(
        f"[bold]Pre-open lane readiness[/] — {response.session_date}  "
        f"(as of {response.as_of.strftime('%H:%M')} WIB)"
    )

    if response.eligibility is SessionEligibility.NOT_A_TRADING_SESSION:
        console.print("  [dim]not a trading session — nothing to capture[/]")
        return

    if response.eligibility is SessionEligibility.NO_CALENDAR_AUTHORITY:
        # Deliberately not silenced: an unattested date is a stale calendar, and
        # suppressing here would fail open on the one lane that cannot be replayed.
        console.print(
            "  [yellow]no calendar authority for this date — checks still run[/]\n"
            "  Fix with: saham fetch market --universe lq45"
        )

    table = Table(header_style="bold")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")

    for row in response.rows:
        table.add_row(
            row.check.value,
            f"[{_STATUS_STYLE[row.status]}]{row.status.value}[/]",
            row.detail,
        )
    console.print(table)

    if response.on_track:
        console.print("  [green]ON TRACK[/]")
        return

    console.print("  [bold red]AT RISK[/] — the NCP window cannot be replayed")
    for row in (*response.at_risk, *response.unknown):
        if row.remediation:
            console.print(f"    {row.check.value}: {row.remediation}")
    if response.eligibility is SessionEligibility.NO_CALENDAR_AUTHORITY:
        # No offline same-day IDX holiday authority exists (see the use case's
        # known-limitation note). Say so, so a holiday false alarm is
        # recognisable as one instead of eroding trust in every later alarm.
        console.print("    [dim]If today is an IDX public holiday, this alarm is expected.[/]")


def _to_dict(response: PreOpenLaneReadinessResponse) -> dict:
    return {
        "session_date": response.session_date.isoformat(),
        "as_of": response.as_of.isoformat(),
        "eligibility": response.eligibility.value,
        "on_track": response.on_track,
        "calendar_snapshot_ids": list(response.calendar_snapshot_ids),
        "checks": [
            {
                "check": row.check.value,
                "status": row.status.value,
                "detail": row.detail,
                "remediation": row.remediation,
            }
            for row in response.rows
        ],
    }


def _resolve_as_of(raw: str | None, session_date: date | None) -> datetime:
    now = datetime.now(IDX_TIMEZONE)
    if raw is None:
        return now
    parsed = _parse_time(raw, "--as-of")
    return datetime.combine(session_date or now.date(), parsed, tzinfo=IDX_TIMEZONE)


def _parse_time(raw: str, flag: str) -> time:
    try:
        return time.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(f"{flag} must be HH:MM, got '{raw}'.") from exc


def _parse_date(raw: str | None, flag: str) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise typer.BadParameter(f"{flag} must be YYYY-MM-DD, got '{raw}'.") from exc
