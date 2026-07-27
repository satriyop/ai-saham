"""CLI: saham assess pre-open

Post-open assessment of an immutable NCP pre-open plan.
Reads learning_observations + linked track snapshots only — no live prices,
no journal write, no confirmation sidecars.

Layer: Adapter
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.adapters.cli.assess_pre_open_display import display_assess_pre_open, echo_json
from src.adapters.cli.research_pre_open_paths import parse_session_date
from src.application.dto.analyze_pre_open import (
    AnalyzePreOpenAmbiguityError,
    AnalyzePreOpenContractError,
    AnalyzePreOpenError,
    AnalyzePreOpenNotFoundError,
    AnalyzePreOpenRequest,
    AnalyzePreOpenSnapshotError,
)
from src.application.use_case.analyze_pre_open_use_case import AnalyzePreOpenUseCase
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.pre_open_config import load_pre_open_screen_config


def pre_open(
    session: Annotated[
        Optional[str],
        typer.Option(
            "--session",
            help="Session date YYYY-MM-DD (default: today IDX)",
        ),
    ] = None,
    observation_id: Annotated[
        Optional[str],
        typer.Option(
            "--observation-id",
            help="Exact learning observation id (required if multiple cohorts)",
        ),
    ] = None,
    opening_snapshot_id: Annotated[
        Optional[str],
        typer.Option(
            "--opening-snapshot-id",
            help="Exact opening track snapshot id linked to the observation",
        ),
    ] = None,
    db_path: Annotated[
        Optional[Path],
        typer.Option("--db", help="Learning SQLite path"),
    ] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
) -> None:
    """Post-open assessment of NCP pre-open plan (read-only; database-identified)."""
    session_date = parse_session_date(session)
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        SQLiteLearningArtifactRepository,
    )

    repository = SQLiteLearningArtifactRepository(resolved_db)
    use_case = AnalyzePreOpenUseCase(
        observations=repository,
        tracks=repository,
        pre_open_config=load_pre_open_screen_config(),
        clock_date=datetime.now(IDX_TIMEZONE).date(),
    )

    try:
        result = use_case.execute(
            AnalyzePreOpenRequest(
                session_date=session_date,
                observation_id=observation_id,
                opening_snapshot_id=opening_snapshot_id,
            )
        )
    except (
        AnalyzePreOpenNotFoundError,
        AnalyzePreOpenAmbiguityError,
        AnalyzePreOpenSnapshotError,
        AnalyzePreOpenContractError,
        AnalyzePreOpenError,
    ) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    if fmt == "json":
        echo_json(result)
        return
    display_assess_pre_open(result)
