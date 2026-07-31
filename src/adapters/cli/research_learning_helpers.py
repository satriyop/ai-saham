"""Shared helpers for research corpus evaluate/status/labels CLI adapters.

Layer: Adapter
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import typer

from src.application.use_case.database_learning_lifecycle_use_case import (
    EvaluateLearningCohortRequest,
    EvaluateLearningCohortUseCase,
    GetLearningStatusUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)


def repository(
    db_path: Path | None,
) -> tuple[Path, SQLiteLearningArtifactRepository]:
    cfg = load_app_config()
    resolved = db_path or Path(cfg.storage.db_path)
    return resolved, SQLiteLearningArtifactRepository(resolved)


def list_compatibility_ids(
    repo: SQLiteLearningArtifactRepository,
    purpose: AssessmentPurpose,
) -> list[str]:
    """Distinct non-empty compatibility cohorts for a purpose (sorted)."""
    return sorted(
        {
            observation.compatibility_id
            for observation in repo.list_observations(purpose)
            if observation.compatibility_id
        }
    )


def resolve_compatibility_id(
    repo: SQLiteLearningArtifactRepository,
    purpose: AssessmentPurpose,
    requested: str | None,
) -> str:
    """Resolve exactly one cohort for evaluate / single-cohort ops (fail-closed).

    Labels must use :func:`resolve_label_compatibility_ids` so nightly cron can
    cover every fork without requiring ``--compatibility-id``.
    """
    if requested is not None:
        return requested
    available = list_compatibility_ids(repo, purpose)
    if len(available) != 1:
        raise typer.BadParameter(
            "specify --compatibility-id; available cohorts: "
            + (", ".join(available) or "none")
        )
    return available[0]


def resolve_label_compatibility_ids(
    repo: SQLiteLearningArtifactRepository,
    purpose: AssessmentPurpose,
    requested: str | None,
) -> list[str]:
    """Cohorts to label: explicit id, else **all** distinct cohorts independently.

    Label generation is per-observation and idempotent; forking material config
    creates a new ``compatibility_id``. Nightly cron must not die when two
    cohorts coexist — it should label each rulebook separately. Evaluate still
    uses :func:`resolve_compatibility_id` (fail-closed on mixed cohorts).
    """
    if requested is not None:
        return [requested.strip()] if requested.strip() else []
    available = list_compatibility_ids(repo, purpose)
    if not available:
        raise typer.BadParameter(
            f"no observations with compatibility_id for purpose={purpose.value}; "
            "nothing to label"
        )
    return available


def echo(payload: dict, fmt: str) -> None:
    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


def evaluate_cohort(
    purpose: AssessmentPurpose,
    *,
    compatibility_id: str | None,
    db_path: Path | None,
    fmt: str,
) -> None:
    _, repo = repository(db_path)
    cohort = resolve_compatibility_id(repo, purpose, compatibility_id)
    evaluation = EvaluateLearningCohortUseCase(
        observations=repo,
        labels=repo,
        evaluations=repo,
    ).execute(
        EvaluateLearningCohortRequest(
            purpose=purpose,
            compatibility_id=cohort,
            evaluated_at=datetime.now(IDX_TIMEZONE),
        )
    )
    echo(
        {
            "artifact_type": "learning_evaluation",
            "evaluation_id": evaluation.evaluation_id,
            "contract_id": evaluation.contract_id.value,
            "purpose": evaluation.purpose.value,
            "method": evaluation.method.value,
            "compatibility_id": evaluation.compatibility_id,
            "readiness": evaluation.readiness.value,
            "outcome_basis": evaluation.outcome_basis.value,
            "metrics": evaluation.metrics,
        },
        fmt,
    )


def status_cohort(
    purpose: AssessmentPurpose,
    *,
    db_path: Path | None,
    fmt: str,
) -> None:
    _, repo = repository(db_path)
    status = GetLearningStatusUseCase(
        observations=repo,
        labels=repo,
        evaluations=repo,
    ).execute(purpose)
    echo(
        {
            "artifact_type": "learning_status",
            "purpose": purpose.value,
            "observation_count": status.observation_count,
            "label_count": status.label_count,
            "available_label_count": status.available_label_count,
            "evaluation_count": status.evaluation_count,
            "compatibility_ids": list(status.compatibility_ids),
        },
        fmt,
    )
