"""CLI: research pre-open evaluate + session status (corpus readiness).

Layer: Adapter
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.research_learning_helpers import (
    echo,
    evaluate_cohort,
    repository,
)
from src.adapters.cli.research_pre_open_paths import parse_session_date
from src.application.use_case.database_learning_lifecycle_use_case import (
    GetPreOpenSessionStatusUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import AssessmentPurpose


def pre_open_evaluate(
    compatibility_id: Annotated[Optional[str], typer.Option("--compatibility-id")] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Evaluate persisted pre-open labels without rereading tracks."""

    evaluate_cohort(
        AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        compatibility_id=compatibility_id,
        db_path=db_path,
        fmt=fmt,
    )


def pre_open_status(
    session: Annotated[
        Optional[str],
        typer.Option(
            "--session",
            help="Session date YYYY-MM-DD (default: today IDX)",
        ),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Show pre-open session readiness (capture / track open / labels)."""

    session_date = parse_session_date(session) or datetime.now(IDX_TIMEZONE).date()
    _, repo = repository(db_path)
    status = GetPreOpenSessionStatusUseCase(
        observations=repo,
        tracks=repo,
        labels=repo,
        evaluations=repo,
    ).execute(session_date)
    payload = {
        "artifact_type": "pre_open_session_status",
        "session_date": status.session_date.isoformat(),
        "observation_count": status.observation_count,
        "with_opening_price": status.with_opening_price,
        "missing_opening_price": status.missing_opening_price,
        "labeled_count": status.labeled_count,
        "next_actions": list(status.next_actions),
        "lines": [
            {
                "ticker": line.ticker,
                "observation_id": line.observation_id,
                "screen_result": line.screen_result,
                "track_count": line.track_count,
                "has_opening_price": line.has_opening_price,
                "opening_snapshot_id": line.opening_snapshot_id,
                "label_available": line.label_available,
                "readiness": line.readiness,
            }
            for line in status.lines
        ],
        "corpus": {
            "observation_count": status.corpus.observation_count,
            "label_count": status.corpus.label_count,
            "available_label_count": status.corpus.available_label_count,
            "evaluation_count": status.corpus.evaluation_count,
            "compatibility_ids": list(status.corpus.compatibility_ids),
        },
    }
    if fmt == "json":
        echo(payload, fmt)
        return
    typer.echo(f"Pre-open session status  {status.session_date.isoformat()}")
    typer.echo(
        f"  observations: {status.observation_count}  "
        f"with_open: {status.with_opening_price}  "
        f"missing_open: {status.missing_opening_price}  "
        f"labeled: {status.labeled_count}"
    )
    if status.lines:
        typer.echo("  lines:")
        for line in status.lines:
            obs_id = line.observation_id
            snap = line.opening_snapshot_id or "-"
            obs_s = obs_id if len(obs_id) <= 14 else obs_id[:12] + "…"
            snap_s = snap if snap == "-" or len(snap) <= 14 else snap[:12] + "…"
            typer.echo(
                f"    {line.ticker:6}  {line.readiness:16}  "
                f"tracks={line.track_count}  open={line.has_opening_price}  "
                f"obs={obs_s}  snap={snap_s}"
            )
    for action in status.next_actions:
        typer.echo(f"  → {action}")
    typer.echo(
        f"  corpus_all_time: obs={status.corpus.observation_count} "
        f"labels={status.corpus.label_count} "
        f"evals={status.corpus.evaluation_count}"
    )
