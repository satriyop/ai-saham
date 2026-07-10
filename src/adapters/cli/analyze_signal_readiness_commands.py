"""
CLI commands for SignalEngine target readiness reporting.

Layer: Adapter
"""

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.report_signal_readiness_use_case import (
    ReportSignalReadinessRequest,
    ReportSignalReadinessUseCase,
    SignalReadinessReport,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)

DEFAULT_DB_PATH = Path(APP_CFG.storage.db_path)


def signal_readiness(
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help=(
                "Calibration target, e.g. "
                "foreign_institutional_accumulation_large_cap_SWING_10D"
            ),
        ),
    ],
    fmt: Annotated[str, typer.Option("--format", help="Output format: table or json")] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Report read-only Phase I observation/label readiness for one target."""
    resolved_db = db_path or DEFAULT_DB_PATH
    try:
        report = ReportSignalReadinessUseCase(
            candidate_observations_repository=SQLiteCandidateObservationsRepository(
                resolved_db
            ),
            signal_forward_labels_repository=SQLiteSignalForwardLabelsRepository(
                resolved_db
            ),
        ).execute(ReportSignalReadinessRequest(target=target))
    except ValueError as exc:
        typer.echo(f"[error] Invalid target: {exc}", err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"[error] Failed to build readiness report: {exc}", err=True)
        raise typer.Exit(1)

    if fmt == "json":
        typer.echo(json.dumps(report.to_dict(), indent=2))
        return
    _display_readiness_report(report)


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}%"


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "—"
    if value == float("inf"):
        return "Infinity"
    return f"{value:.2f}"


def _display_readiness_report(report: SignalReadinessReport) -> None:
    typer.echo(f"\nSignal Readiness · {report.target.raw}")
    typer.echo("═" * 78)
    cap_display = (
        report.target.market_cap_bucket
        if report.target.market_cap_bucket is not None
        else "any (diagnostic — no cap filter)"
    )
    typer.echo(
        "Target: "
        f"profile={report.target.profile}, "
        f"setup={report.target.setup_family}, "
        f"cap={cap_display}, "
        f"horizon={report.target.horizon.value}"
    )
    if report.target.is_diagnostic:
        typer.echo(
            "[DIAGNOSTIC] market-cap bucket not required; "
            "canonical large-cap target remains blocked."
        )
    dates = (
        ", ".join(day.isoformat() for day in report.observation_dates)
        if report.observation_dates
        else "none"
    )
    latest_date = (
        report.latest_observation_date.isoformat()
        if report.latest_observation_date
        else "none"
    )
    typer.echo(f"Observation dates: {dates}")
    typer.echo(f"Latest observation date: {latest_date}")
    typer.echo(f"Latest per-ticker observations: {report.latest_observation_count}")
    typer.echo(f"Raw latest observation rows: {report.raw_latest_observation_count}")
    typer.echo(f"Target-filter count: {report.target_filter_count}")
    typer.echo(f"Raw target-filter rows: {report.raw_target_filter_count}")
    if report.notes:
        typer.echo("")
        typer.echo("Notes:")
        for note in report.notes:
            typer.echo(f"  - {note}")
    typer.echo("")
    typer.echo(f"Label count: {report.label_count}")
    typer.echo(f"Unavailable label count: {report.unavailable_label_count}")
    typer.echo(f"Target label count: {report.target_label_count}")
    typer.echo(f"Labeled target count: {report.labeled_target_count}")
    typer.echo("")
    typer.echo(
        "IS/OOS: "
        f"IS={report.is_count}, OOS={report.oos_count}, "
        f"diagnostic_ready={report.diagnostic_ready}, "
        f"patch_eligible={report.patch_eligible}"
    )
    typer.echo(
        "OOS metrics: "
        f"profit_factor={_fmt_number(report.oos_profit_factor)}, "
        f"avg_return={_fmt_pct(report.oos_average_return)}"
    )
    if report.blockers:
        typer.echo("")
        typer.echo("Why not patch-eligible:")
        for blocker in report.blockers:
            typer.echo(f"  - {blocker}")
    else:
        typer.echo("")
        typer.echo("Patch eligibility gates passed for this read-only report.")
