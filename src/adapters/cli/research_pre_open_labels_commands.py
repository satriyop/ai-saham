"""
CLI: saham research pre-open labels

Generate open_30m outcome labels from saved pre-open observations and tracks.
Session-horizon twin of research signal labels (multi-day); separate command
so agents never mix open_30m into SignalLabelHorizon pipelines.

Layer: Adapter
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.database_learning_lifecycle_use_case import (
    GenerateLearningLabelsRequest,
    GeneratePreOpenOutcomeLabelsUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
)
from src.infrastructure.config.app_config import load_app_config


def pre_open_labels(
    compatibility_id: Annotated[
        Optional[str],
        typer.Option("--compatibility-id", help="Exact compatible cohort identity"),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
) -> None:
    """
    Generate immutable open_30m labels for one compatible database cohort.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        SQLiteLearningArtifactRepository,
    )

    repository = SQLiteLearningArtifactRepository(resolved_db)
    observations = repository.list_observations(
        AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION
    )
    compatibility_ids = sorted(
        {observation.compatibility_id for observation in observations}
    )
    if compatibility_id is None:
        if len(compatibility_ids) != 1:
            typer.echo(
                "Specify --compatibility-id; available cohorts: "
                + (", ".join(compatibility_ids) or "none"),
                err=True,
            )
            raise typer.Exit(1)
        compatibility_id = compatibility_ids[0]
    result = GeneratePreOpenOutcomeLabelsUseCase(
        observations=repository,
        tracks=repository,
        labels=repository,
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            compatibility_id=compatibility_id,
            label_contract=LearningContractId.PRE_OPEN_LABEL,
            labeled_at=datetime.now(IDX_TIMEZONE),
        )
    )

    payload = {
        "artifact_type": "learning_label_generation",
        "purpose": AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION.value,
        "contract_id": LearningContractId.PRE_OPEN_LABEL.value,
        "compatibility_id": compatibility_id,
        "observation_count": result.observation_count,
        "inserted_count": result.inserted_count,
        "idempotent_count": result.idempotent_count,
        "unavailable_count": result.unavailable_count,
        "label_ids": [label.label_id for label in result.labels],
    }
    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2))
        return
    typer.echo(
        "open_30m labels: source=database_tracks  "
        f"n={result.observation_count}  labeled={result.inserted_count}  "
        f"unavailable={result.unavailable_count}"
    )
