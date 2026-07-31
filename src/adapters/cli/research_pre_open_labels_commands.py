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
        typer.Option(
            "--compatibility-id",
            help=(
                "Label only this cohort. When omitted, label every distinct "
                "compatibility_id independently (safe for multi-cohort cron)."
            ),
        ),
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[
        str,
        typer.Option("--format", help="Output format: table or json"),
    ] = "table",
) -> None:
    """
    Generate immutable open_30m labels per compatibility cohort.

    Without ``--compatibility-id``, each cohort is labeled independently.
    """
    cfg = load_app_config()
    resolved_db = db_path or Path(cfg.storage.db_path)

    from src.adapters.cli.research_learning_helpers import resolve_label_compatibility_ids
    from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
        SQLiteLearningArtifactRepository,
    )

    repository = SQLiteLearningArtifactRepository(resolved_db)
    try:
        cohorts = resolve_label_compatibility_ids(
            repository,
            AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
            compatibility_id,
        )
    except typer.BadParameter as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    use_case = GeneratePreOpenOutcomeLabelsUseCase(
        observations=repository,
        tracks=repository,
        labels=repository,
    )
    labeled_at = datetime.now(IDX_TIMEZONE)

    def _one(cohort: str) -> dict:
        result = use_case.execute(
            GenerateLearningLabelsRequest(
                purpose=AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
                compatibility_id=cohort,
                label_contract=LearningContractId.PRE_OPEN_LABEL,
                labeled_at=labeled_at,
            )
        )
        return {
            "compatibility_id": cohort,
            "observation_count": result.observation_count,
            "inserted_count": result.inserted_count,
            "idempotent_count": result.idempotent_count,
            "unavailable_count": result.unavailable_count,
            "skipped_count": result.skipped_count,
            "conflict_count": result.conflict_count,
            "conflict_label_ids": list(result.conflict_label_ids),
            "label_ids": [label.label_id for label in result.labels],
        }

    if len(cohorts) == 1:
        one = _one(cohorts[0])
        payload = {
            "artifact_type": "learning_label_generation",
            "purpose": AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION.value,
            "contract_id": LearningContractId.PRE_OPEN_LABEL.value,
            **one,
        }
        conflict_ids = list(one["conflict_label_ids"])
        if fmt == "json":
            typer.echo(json.dumps(payload, indent=2))
            return
        typer.echo(
            "open_30m labels: source=database_tracks  "
            f"n={one['observation_count']}  labeled={one['inserted_count']}  "
            f"unavailable={one['unavailable_count']}  skipped={one['skipped_count']}  "
            f"conflicts={one['conflict_count']}"
        )
    else:
        cohort_results = [_one(c) for c in cohorts]
        payload = {
            "artifact_type": "learning_label_generation_multi_cohort",
            "purpose": AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION.value,
            "contract_id": LearningContractId.PRE_OPEN_LABEL.value,
            "compatibility_ids": cohorts,
            "cohort_count": len(cohorts),
            "cohorts": cohort_results,
            "inserted_count": sum(c["inserted_count"] for c in cohort_results),
            "skipped_count": sum(c["skipped_count"] for c in cohort_results),
            "conflict_count": sum(c["conflict_count"] for c in cohort_results),
            "observation_count": sum(c["observation_count"] for c in cohort_results),
        }
        conflict_ids = [
            lid for c in cohort_results for lid in c["conflict_label_ids"]
        ]
        if fmt == "json":
            typer.echo(json.dumps(payload, indent=2))
            return
        typer.echo(
            "open_30m labels: multi_cohort  "
            f"cohorts={len(cohorts)}  "
            f"n={payload['observation_count']}  labeled={payload['inserted_count']}  "
            f"unavailable={sum(c['unavailable_count'] for c in cohort_results)}  "
            f"skipped={payload['skipped_count']}  conflicts={payload['conflict_count']}"
        )

    if conflict_ids:
        typer.echo(
            "  note: first-write labels kept for conflict ids "
            f"({', '.join(x[:12] + '…' for x in conflict_ids[:5])})",
            err=True,
        )
