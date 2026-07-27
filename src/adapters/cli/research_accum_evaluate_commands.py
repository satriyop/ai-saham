"""CLI: research accum labels / evaluate / replay / status (corpus).

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
    resolve_compatibility_id,
    status_cohort,
)
from src.application.use_case.database_learning_lifecycle_use_case import (
    GenerateAccumulationPricePathLabelsUseCase,
    GenerateLearningLabelsRequest,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
)
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def accumulation_labels(
    compatibility_id: Annotated[Optional[str], typer.Option("--compatibility-id")] = None,
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

    resolved, repo = repository(db_path)
    cohort = resolve_compatibility_id(
        repo,
        AssessmentPurpose.ACCUMULATION_DISCOVERY,
        compatibility_id,
    )
    try:
        contract = LearningContractId(label_contract)
    except ValueError as exc:
        raise typer.BadParameter("unsupported label contract") from exc
    result = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
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
    echo(
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


def accumulation_evaluate(
    compatibility_id: Annotated[Optional[str], typer.Option("--compatibility-id")] = None,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Evaluate one compatible chronological accumulation cohort."""

    evaluate_cohort(
        AssessmentPurpose.ACCUMULATION_DISCOVERY,
        compatibility_id=compatibility_id,
        db_path=db_path,
        fmt=fmt,
    )


def accumulation_status(
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Show database-owned accumulation lifecycle counts."""

    status_cohort(
        AssessmentPurpose.ACCUMULATION_DISCOVERY,
        db_path=db_path,
        fmt=fmt,
    )


def accumulation_replay(
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """List immutable accumulation evaluations available for replay inspection."""

    _, repo = repository(db_path)
    evaluations = repo.list_evaluations(AssessmentPurpose.ACCUMULATION_DISCOVERY)
    echo(
        {
            "artifact_type": "learning_evaluation_catalog",
            "purpose": AssessmentPurpose.ACCUMULATION_DISCOVERY.value,
            "evaluation_ids": [evaluation.evaluation_id for evaluation in evaluations],
        },
        fmt,
    )
