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
from src.application.use_case.get_accumulation_producer_readiness_use_case import (
    GetAccumulationProducerReadinessUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactReadRepository,
    SQLiteLearningArtifactRepository,
)


def repository(
    db_path: Path | None,
) -> tuple[Path, SQLiteLearningArtifactRepository]:
    cfg = load_app_config()
    resolved = db_path or Path(cfg.storage.db_path)
    return resolved, SQLiteLearningArtifactRepository(resolved)


def read_only_repository(
    db_path: Path | None,
) -> tuple[Path, SQLiteLearningArtifactReadRepository]:
    """Status/read paths: never create DB files or run schema ensure."""
    cfg = load_app_config()
    resolved = db_path or Path(cfg.storage.db_path)
    return resolved, SQLiteLearningArtifactReadRepository(resolved)


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
            "specify --compatibility-id; available cohorts: " + (", ".join(available) or "none")
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
            f"no observations with compatibility_id for purpose={purpose.value}; nothing to label"
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
    if purpose is AssessmentPurpose.ACCUMULATION_DISCOVERY:
        try:
            _, read_repo = read_only_repository(db_path)
        except FileNotFoundError as exc:
            raise typer.BadParameter(str(exc)) from exc
        report = GetAccumulationProducerReadinessUseCase(
            observations=read_repo,
            labels=read_repo,
            policy_snapshots=read_repo,
        ).execute(purpose)
        payload = report.to_dict()
        if fmt != "json":
            _echo_producer_readiness_table(payload)
            return
        echo(payload, fmt)
        return

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


def _echo_producer_readiness_table(payload: dict) -> None:
    """Human-readable table for accumulation producer readiness."""
    typer.echo(f"artifact_type: {payload.get('artifact_type')}")
    typer.echo(f"purpose: {payload.get('purpose')}")
    typer.echo(
        f"active_snapshot_binding_contract: {payload.get('active_snapshot_binding_contract')}"
    )
    typer.echo(f"observation_count: {payload.get('observation_count')}")
    typer.echo(f"cohort_count: {payload.get('cohort_count')}")
    typer.echo("")
    for cohort in payload.get("cohorts") or []:
        typer.echo(f"--- cohort {cohort.get('compatibility_id')} ---")
        for key in (
            "producer_status",
            "observation_contract",
            "observation_count",
            "session_count",
            "economic_date_min",
            "economic_date_max",
            "snapshot_binding_contract",
            "snapshot_verified_count",
            "snapshot_required_count",
            "snapshot_missing_policy_ids",
            "snapshot_extra_policy_ids",
            "snapshot_invalid_policy_ids",
            "labels_by_horizon",
            "action_distribution",
            "setup_readiness_present",
            "setup_readiness_missing",
            "setup_readiness_state_distribution",
        ):
            typer.echo(f"{key}: {cohort.get(key)}")
        typer.echo("")
