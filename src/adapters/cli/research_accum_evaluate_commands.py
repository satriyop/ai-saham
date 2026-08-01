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
from src.application.services.trading_session_calendar_selection import (
    assert_no_calendar_source_conflicts,
    select_calendar_snapshot,
)
from src.application.use_case.database_learning_lifecycle_use_case import (
    ACCUM_PATH_LABEL_CONTRACTS,
    ACCUM_PRIMARY_LABEL_CONTRACT,
    GenerateAccumulationPricePathLabelsUseCase,
    GenerateLearningLabelsRequest,
)
from src.application.use_case.sync_trading_session_calendar_snapshot_use_case import (
    ResolveCalendarSyncCoverageRequest,
    ResolveTradingSessionCalendarSyncCoverageUseCase,
    SyncTradingSessionCalendarRequest,
    SyncTradingSessionCalendarSnapshotUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.learning_artifacts import (
    AssessmentPurpose,
    LearningContractError,
    LearningContractId,
)
from src.infrastructure.browser.stockbit_config_bundle import load_stockbit_provider_config
from src.infrastructure.composition import stockbit_session_factory as _stockbit_session
from src.infrastructure.data_providers.stockbit_trading_session_calendar_source import (
    StockbitTradingSessionCalendarSource,
)
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.sqlite_trading_session_calendar_snapshot_repository import (
    SQLiteTradingSessionCalendarSnapshotRepository,
)


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
    # Immutable Stockbit-attested calendar snapshots already persisted for the cohort.
    # Never re-range a growing IHSG candle cache for label identity.
    calendar_store = SQLiteTradingSessionCalendarSnapshotRepository(resolved)
    snapshots = tuple(calendar_store.list_snapshots())
    # Authority conflict is not an ordinary skip — fail the command (and cron).
    try:
        assert_no_calendar_source_conflicts(snapshots)
    except LearningContractError as exc:
        typer.echo(f"calendar source conflict: {exc}", err=True)
        raise typer.Exit(1) from exc

    def _resolve_snapshot(signal_date, horizon_days):
        # Propagates LearningContractError on conflict (must not map to None/skip).
        return select_calendar_snapshot(
            snapshots,
            signal_date=signal_date,
            horizon_days=horizon_days,
        )

    use_case = GenerateAccumulationPricePathLabelsUseCase(
        observations=repo,
        labels=repo,
        market_data=market,
        corporate_actions=SQLiteCorporateActionCalendarRepository(resolved),
        session_snapshot_resolver=_resolve_snapshot,
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


def accumulation_sync_session_calendar(
    start: Annotated[
        Optional[str],
        typer.Option("--start", help="Coverage start YYYY-MM-DD (required unless --auto)"),
    ] = None,
    end: Annotated[
        Optional[str],
        typer.Option("--end", help="Coverage end YYYY-MM-DD (required unless --auto)"),
    ] = None,
    auto: Annotated[
        bool,
        typer.Option(
            "--auto",
            help=(
                "Resolve coverage from earliest unlabeled current-schema observation "
                "through --end (or today in IDX timezone)."
            ),
        ),
    ] = False,
    db_path: Annotated[Optional[Path], typer.Option("--db")] = None,
    fmt: Annotated[str, typer.Option("--format")] = "table",
) -> None:
    """Strict Stockbit IHSG calendar sync → immutable snapshot row.

    Production path for trading_session_calendar_snapshots. Cron runs this
    between capture and labels.

    Ordering: open learning repo → resolve auto coverage (no-op without Stockbit)
    → authenticate → write snapshot. Auto no-op must not require login or create tables.
    """
    from datetime import date as date_cls

    # 1) Learning repo only (may create learning schema via write repo; not snapshot table).
    resolved, repo = repository(db_path)

    # 2) Resolve coverage before Stockbit auth / snapshot writer construction.
    if auto:
        end_date = date_cls.fromisoformat(end) if end else datetime.now(IDX_TIMEZONE).date()
        try:
            coverage = ResolveTradingSessionCalendarSyncCoverageUseCase(
                observations=repo,
                labels=repo,
            ).execute(ResolveCalendarSyncCoverageRequest(end_date=end_date))
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        if coverage.no_op:
            payload = {
                "artifact_type": "trading_session_calendar_sync",
                "no_op": True,
                "no_op_reason": coverage.no_op_reason,
                "eligible_observation_count": coverage.eligible_observation_count,
            }
            echo(payload, fmt)
            return
        assert coverage.coverage_start is not None and coverage.coverage_end is not None
        cov_start, cov_end = coverage.coverage_start, coverage.coverage_end
    else:
        if not start or not end:
            raise typer.BadParameter("provide --start and --end, or use --auto")
        try:
            cov_start = date_cls.fromisoformat(start)
            cov_end = date_cls.fromisoformat(end)
        except ValueError as exc:
            typer.echo(f"invalid date: {exc}", err=True)
            raise typer.Exit(1) from exc
        if cov_start > cov_end:
            typer.echo("coverage_start must not be after coverage_end", err=True)
            raise typer.Exit(1)

    # 3) Authenticate Stockbit only when a real sync will run.
    stockbit_config = load_stockbit_provider_config()
    session = _stockbit_session.get_stockbit_session(stockbit_config)
    if not session or not session.authenticated:
        raise typer.BadParameter(
            "Stockbit session expired. Run `saham fetch stockbit login` to refresh."
        )
    source = StockbitTradingSessionCalendarSource(
        session.api_client,
        stockbit_config=stockbit_config,
        captured_at=datetime.now(IDX_TIMEZONE),
    )
    snap_repo = SQLiteTradingSessionCalendarSnapshotRepository(resolved)
    sync_uc = SyncTradingSessionCalendarSnapshotUseCase(
        source=source,
        snapshots=snap_repo,
    )

    try:
        result = sync_uc.execute(
            SyncTradingSessionCalendarRequest(
                coverage_start=cov_start,
                coverage_end=cov_end,
            )
        )
    except LearningContractError as exc:
        typer.echo(f"calendar sync failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    payload = {
        "artifact_type": "trading_session_calendar_sync",
        "snapshot_id": result.snapshot_id,
        "inserted": result.inserted,
        "session_count": result.session_count,
        "coverage_start": result.coverage_start.isoformat(),
        "coverage_end": result.coverage_end.isoformat(),
        "no_op": False,
    }
    echo(payload, fmt)


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
