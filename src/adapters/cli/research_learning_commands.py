"""Thin CLI adapters for database-owned learning labels/evaluations/status."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer

from src.application.use_case.database_learning_lifecycle_use_case import (
    EvaluateLearningCohortRequest,
    EvaluateLearningCohortUseCase,
    GenerateAccumulationPricePathLabelsUseCase,
    GenerateLearningLabelsRequest,
    GetLearningStatusUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)
from src.infrastructure.persistence.sqlite_learning_artifact_repository import (
    SQLiteLearningArtifactRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def _repository(db_path: Path | None) -> tuple[Path, SQLiteLearningArtifactRepository]:
    cfg = load_app_config()
    resolved = db_path or Path(cfg.storage.db_path)
    return resolved, SQLiteLearningArtifactRepository(resolved)


def _resolve_compatibility_id(
    repository: SQLiteLearningArtifactRepository,
    purpose: AssessmentPurpose,
    requested: str | None,
) -> str:
    if requested is not None:
        return requested
    available = sorted(
        {
            observation.compatibility_id
            for observation in repository.list_observations(purpose)
        }
    )
    if len(available) != 1:
        raise typer.BadParameter(
            "specify --compatibility-id; available cohorts: "
            + (", ".join(available) or "none")
        )
    return available[0]


def _echo(payload: dict, fmt: str) -> None:
    if fmt == "json":
        typer.echo(json.dumps(payload, indent=2))
        return
    for key, value in payload.items():
        typer.echo(f"{key}: {value}")


def accumulation_labels(
    compatibility_id: Annotated[
        Optional[str], typer.Option("--compatibility-id")
    ] = None,
    label_contract: Annotated[
        str,
        typer.Option(
            "--label-contract",
            help="price_path.tactical_3d.v1, swing_10d.v1, or accum_20d.v1",
        ),
    ] = LearningContractId.ACCUMULATION_LABEL.value,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Generate immutable price-path labels from accumulation observations."""

    resolved, repository = _repository(db_path)
    cohort = _resolve_compatibility_id(
        repository,
        AssessmentPurpose.ACCUMULATION_DISCOVERY,
        compatibility_id,
    )
    try:
        contract = LearningContractId(label_contract)
    except ValueError as exc:
        raise typer.BadParameter("unsupported label contract") from exc
    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repository,
        labels=repository,
        market_data=SQLiteMarketRepository(resolved),
        corporate_actions=SQLiteCorporateActionCalendarRepository(resolved),
    ).execute(
        GenerateLearningLabelsRequest(
            purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
            compatibility_id=cohort,
            label_contract=contract,
            labeled_at=datetime.now(IDX_TIMEZONE),
        )
    )
    _echo(
        {
            "artifact_type": "learning_label_generation",
            "contract_id": contract.value,
            "compatibility_id": cohort,
            "observation_count": result.observation_count,
            "inserted_count": result.inserted_count,
            "idempotent_count": result.idempotent_count,
            "unavailable_count": result.unavailable_count,
            "label_ids": [label.label_id for label in result.labels],
        },
        fmt,
    )

def _evaluate(
    purpose: AssessmentPurpose,
    *,
    compatibility_id: str | None,
    db_path: Path | None,
    fmt: str,
) -> None:
    _, repository = _repository(db_path)
    cohort = _resolve_compatibility_id(repository, purpose, compatibility_id)
    evaluation = EvaluateLearningCohortUseCase(
        observations=repository,
        labels=repository,
        evaluations=repository,
    ).execute(
        EvaluateLearningCohortRequest(
            purpose=purpose,
            compatibility_id=cohort,
            evaluated_at=datetime.now(IDX_TIMEZONE),
        )
    )
    _echo(
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


def accumulation_evaluate(
    compatibility_id: Annotated[
        Optional[str], typer.Option("--compatibility-id")
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Evaluate one compatible chronological accumulation cohort."""

    _evaluate(
        AssessmentPurpose.ACCUMULATION_DISCOVERY,
        compatibility_id=compatibility_id,
        db_path=db_path,
        fmt=fmt,
    )


def pre_open_evaluate(
    compatibility_id: Annotated[
        Optional[str], typer.Option("--compatibility-id")
    ] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Evaluate persisted pre-open labels without rereading tracks."""

    _evaluate(
        AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        compatibility_id=compatibility_id,
        db_path=db_path,
        fmt=fmt,
    )


def _status(
    purpose: AssessmentPurpose,
    *,
    db_path: Path | None,
    fmt: str,
) -> None:
    _, repository = _repository(db_path)
    status = GetLearningStatusUseCase(
        observations=repository,
        labels=repository,
        evaluations=repository,
    ).execute(purpose)
    _echo(
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


def accumulation_status(
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Show database-owned accumulation lifecycle counts."""

    _status(
        AssessmentPurpose.ACCUMULATION_DISCOVERY,
        db_path=db_path,
        fmt=fmt,
    )


def pre_open_status(
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Show database-owned pre-open lifecycle counts."""

    _status(
        AssessmentPurpose.PRE_OPEN_AUCTION_DIRECTION,
        db_path=db_path,
        fmt=fmt,
    )


def accumulation_replay(
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """List immutable accumulation evaluations available for replay inspection."""

    _, repository = _repository(db_path)
    evaluations = repository.list_evaluations(
        AssessmentPurpose.ACCUMULATION_DISCOVERY
    )
    _echo(
        {
            "artifact_type": "learning_evaluation_catalog",
            "purpose": AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
            "evaluation_ids": [
                evaluation.evaluation_id for evaluation in evaluations
            ],
        },
        fmt,
    )
