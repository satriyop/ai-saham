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
    resolve_label_compatibility_ids,
    status_cohort,
)
from src.application.use_case.database_learning_lifecycle_use_case import (
    ACCUM_PATH_LABEL_CONTRACTS,
    ACCUM_PRIMARY_LABEL_CONTRACT,
    GenerateAccumulationPricePathLabelsUseCase,
    GenerateLearningLabelsRequest,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractId,
)
from src.infrastructure.persistence.ihsg_candle_session_calendar import (
    load_ihsg_candle_session_calendar,
)
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository


def accumulation_labels(
    compatibility_id: Annotated[
        Optional[str],
        typer.Option(
            "--compatibility-id",
            help=(
                "Label only this cohort. When omitted, label **every** distinct "
                "compatibility_id independently (safe for cron after config forks)."
            ),
        ),
    ] = None,
    label_contract: Annotated[
        Optional[str],
        typer.Option(
            "--label-contract",
            help=(
                "Single contract: price_path.accum_3d.v1, accum_10d.v1 (primary), "
                "or accum_20d.v1. Default accum_10d when --all-label-contracts is off."
            ),
        ),
    ] = None,
    all_label_contracts: Annotated[
        bool,
        typer.Option(
            "--all-label-contracts",
            help=(
                "Run all accum path label contracts (accum_3d, accum_10d, accum_20d). "
                "Incompatible with an explicit --label-contract."
            ),
        ),
    ] = False,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Generate immutable price-path labels from accumulation observations.

    Without ``--compatibility-id``, each compatibility cohort is labeled
    independently (nightly cron must survive multi-cohort corpora).
    """

    if all_label_contracts and label_contract is not None:
        raise typer.BadParameter("use either --all-label-contracts or --label-contract, not both")
    if all_label_contracts:
        contracts: tuple[LearningContractId, ...] = ACCUM_PATH_LABEL_CONTRACTS
    else:
        raw = label_contract or ACCUM_PRIMARY_LABEL_CONTRACT.value
        try:
            contracts = (LearningContractId(raw),)
        except ValueError as exc:
            raise typer.BadParameter("unsupported label contract") from exc
        if contracts[0] not in ACCUM_PATH_LABEL_CONTRACTS:
            raise typer.BadParameter(
                "accum labels only accept " + ", ".join(c.value for c in ACCUM_PATH_LABEL_CONTRACTS)
            )

    resolved, repo = repository(db_path)
    cohorts = resolve_label_compatibility_ids(
        repo,
        AssessmentPurpose.ACCUMULATION_DISCOVERY,
        compatibility_id,
    )
    market = SQLiteMarketRepository(resolved)
    # Same IHSG-candle session authority as readiness (full cached IHSG span).
    session_calendar = None
    for ticker in ("IHSG", "^JKSE"):
        span = market.get_date_range(ticker)
        if span is not None:
            session_calendar = load_ihsg_candle_session_calendar(
                market,
                coverage_start=span[0],
                coverage_end=span[1],
            )
            if session_calendar is not None:
                break
    use_case = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
        market_data=market,
        corporate_actions=SQLiteCorporateActionCalendarRepository(resolved),
        session_calendar=session_calendar,
    )
    labeled_at = datetime.now(IDX_TIMEZONE)

    def _run_contracts(cohort: str) -> list[dict]:
        results: list[dict] = []
        for contract in contracts:
            result = use_case.execute(
                GenerateLearningLabelsRequest(
                    purpose=AssessmentPurpose.ACCUMULATION_DISCOVERY,
                    compatibility_id=cohort,
                    label_contract=contract,
                    labeled_at=labeled_at,
                )
            )
            results.append(
                {
                    "contract_id": contract.value,
                    "observation_count": result.observation_count,
                    "inserted_count": result.inserted_count,
                    "idempotent_count": result.idempotent_count,
                    "unavailable_count": result.unavailable_count,
                    "skipped_count": result.skipped_count,
                    "conflict_count": result.conflict_count,
                    "conflict_label_ids": list(result.conflict_label_ids),
                    "label_ids": [label.label_id for label in result.labels],
                }
            )
        return results

    if len(cohorts) == 1:
        cohort = cohorts[0]
        results = _run_contracts(cohort)
        if len(results) == 1:
            payload = {
                "artifact_type": "learning_label_generation",
                "compatibility_id": cohort,
                **results[0],
            }
        else:
            payload = {
                "artifact_type": "learning_label_generation_batch",
                "compatibility_id": cohort,
                "contracts": [r["contract_id"] for r in results],
                "results": results,
                "inserted_count": sum(r["inserted_count"] for r in results),
                "skipped_count": sum(r["skipped_count"] for r in results),
                "conflict_count": sum(r["conflict_count"] for r in results),
            }
        echo(payload, fmt)
        return

    # Multi-cohort: label each independently (never pool rulebooks).
    cohort_payloads = []
    for cohort in cohorts:
        results = _run_contracts(cohort)
        cohort_payloads.append(
            {
                "compatibility_id": cohort,
                "contracts": [r["contract_id"] for r in results],
                "results": results,
                "inserted_count": sum(r["inserted_count"] for r in results),
                "skipped_count": sum(r["skipped_count"] for r in results),
                "conflict_count": sum(r["conflict_count"] for r in results),
                "observation_count": sum(r["observation_count"] for r in results),
            }
        )
    payload = {
        "artifact_type": "learning_label_generation_multi_cohort",
        "compatibility_ids": cohorts,
        "cohort_count": len(cohorts),
        "cohorts": cohort_payloads,
        "inserted_count": sum(c["inserted_count"] for c in cohort_payloads),
        "skipped_count": sum(c["skipped_count"] for c in cohort_payloads),
        "conflict_count": sum(c["conflict_count"] for c in cohort_payloads),
    }
    echo(payload, fmt)


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
