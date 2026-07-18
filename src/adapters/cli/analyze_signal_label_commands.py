"""
CLI commands for persisting and summarizing signal forward labels.

Layer: Adapter
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.generate_signal_forward_labels_use_case import (
    GenerateAllSignalForwardLabelsRequest,
    GenerateEligibleSignalForwardLabelsRequest,
    GenerateSignalForwardLabelsRequest,
    GenerateSignalForwardLabelsUseCase,
    SignalLabelGenerationSkipReason,
)
from src.application.use_case.summarize_signal_forward_labels_use_case import (
    SummarizeSignalForwardLabelsRequest,
    SummarizeSignalForwardLabelsUseCase,
)
from src.domain.value_objects.signal_artifact_schema import (
    CANDIDATE_OBSERVATION_SCHEMA_VERSION,
)
from src.domain.value_objects.signal_forward_label import SignalLabelHorizon
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_signal_forward_labels_repository import (
    SQLiteSignalForwardLabelsRepository,
)


def signal_labels(
    snapshot_date: Annotated[
        Optional[str],
        typer.Argument(help="Signal date YYYY-MM-DD; omit with --eligible-dates"),
    ] = None,
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
    generate_all: Annotated[
        bool,
        typer.Option(
            "--generate-all",
            help="Generate labels for all latest observations on the date before summarizing",
        ),
    ] = False,
    eligible_dates: Annotated[
        bool,
        typer.Option(
            "--eligible-dates",
            help="With --generate-all, generate labels for saved dates with enough forward candles",
        ),
    ] = False,
    captured_at: Annotated[
        Optional[str],
        typer.Option("--captured-at", help="Specific observation timestamp ISO-8601"),
    ] = None,
    fmt: Annotated[str, typer.Option("--format", help="Output format: table or json")] = "table",
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
) -> None:
    """Generate and summarize persisted signal forward labels."""
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)
    day: date | None = None
    if snapshot_date is not None:
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

    if generate and generate_all:
        typer.echo("[error] Use either --generate or --generate-all, not both.", err=True)
        raise typer.Exit(1)
    if generate_all and ticker_u:
        typer.echo("[error] --ticker is not supported with --generate-all.", err=True)
        raise typer.Exit(1)
    if generate_all and captured_dt is not None:
        typer.echo("[error] --captured-at is not supported with --generate-all.", err=True)
        raise typer.Exit(1)
    if eligible_dates and not generate_all:
        typer.echo("[error] --eligible-dates requires --generate-all.", err=True)
        raise typer.Exit(1)
    if eligible_dates and snapshot_date is not None:
        typer.echo("[error] Do not pass a date with --eligible-dates.", err=True)
        raise typer.Exit(1)
    if not eligible_dates and day is None:
        typer.echo(
            "[error] Signal date YYYY-MM-DD is required unless --eligible-dates is used.",
            err=True,
        )
        raise typer.Exit(1)

    if generate:
        if not ticker_u:
            typer.echo("[error] --ticker is required with --generate", err=True)
            raise typer.Exit(1)
        assert day is not None
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
        if response.skip_reason is SignalLabelGenerationSkipReason.INCOMPATIBLE_OBSERVATION_SCHEMA:
            found = (
                str(response.source_schema_version)
                if response.source_schema_version is not None
                else "missing-or-invalid"
            )
            typer.echo(
                f"[error] Stored observation for {ticker_u} on {day} is not canonical: "
                f"expected schema {CANDIDATE_OBSERVATION_SCHEMA_VERSION}, found {found}. "
                "No label was generated.",
                err=True,
            )
            raise typer.Exit(1)
        if response.skip_reason is SignalLabelGenerationSkipReason.NON_CANONICAL_OBSERVATION_IDENTITY:
            typer.echo(
                f"[error] Stored observation for {ticker_u} on {day} has no canonical "
                "config_hash. No label was generated.",
                err=True,
            )
            raise typer.Exit(1)
        if fmt != "json":
            label = response.labels[0]
            typer.echo(
                f"Generated {label.horizon.value} label for {label.ticker} "
                f"{label.signal_date}: {label.outcome_label.value}"
            )

    if generate_all:
        generator = GenerateSignalForwardLabelsUseCase(
            candidate_observations_repository=SQLiteCandidateObservationsRepository(resolved_db),
            market_data_repository=SQLiteMarketRepository(resolved_db),
            signal_forward_labels_repository=labels_repo,
        )
        if eligible_dates:
            response = generator.execute_eligible_dates(
                GenerateEligibleSignalForwardLabelsRequest(horizon=label_horizon)
            )
        else:
            assert day is not None
            response = generator.execute_all(
                GenerateAllSignalForwardLabelsRequest(
                    signal_date=day,
                    horizons=(label_horizon,),
                )
            )
        if fmt != "json":
            typer.echo(
                f"Generated {response.generated_count} {label_horizon.value} labels "
                f"from {response.observation_count} observations "
                f"({response.unavailable_count} unavailable, "
                f"{response.skipped_incompatible_observation_count} incompatible "
                "observations skipped)."
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


def _fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}%"


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
