"""
Adapter composition root/factory for the log accumulation trade workflow.

Layer: Adapter
"""

from pathlib import Path
from typing import Optional

from src.adapters.composition.stock_analysis_workflow_dependencies import (
    StockAnalysisWorkflowDependencies,
    create_stock_analysis_workflow_dependencies,
)
from src.application.services.accumulation_journal import AccumulationJournalService
from src.application.services.accumulation_screen_factory import (
    create_accumulation_screen_use_case,
)
from src.application.use_case.evaluate_swing_setup_use_case import AVAILABLE_SWING_SETUPS
from src.application.use_case.log_accumulation_trade_workflow_use_case import (
    LogAccumulationTradeWorkflowBundle,
    LogAccumulationTradeWorkflowUseCase,
    build_log_accumulation_trade_policy,
)
from src.application.use_case.log_swing_candidate_use_case import (
    LogSwingCandidateUseCase,
)
from src.infrastructure.config.app_config import load_app_config
from src.infrastructure.config.market_context_factory import create_market_context_engine
from src.infrastructure.config.swing_backtest_config import load_swing_backtest_config
from src.infrastructure.config.swing_policy_config_loader import load_swing_policy_config
from src.infrastructure.persistence.accumulation_journal_csv_writer import (
    AccumulationJournalCsvWriter,
)
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.trade_journal_jsonl_writer import TradeJournalJsonlWriter


def create_log_accumulation_trade_workflow(
    *,
    db_path: Path,
    journal_path: Path,
    with_regime: bool,
    regime_universe: Optional[str],
    benchmark: str,
    dependencies: StockAnalysisWorkflowDependencies | None = None,
) -> LogAccumulationTradeWorkflowBundle:
    """Wire up all repository, service, and engine dependencies for log swing trade workflow."""
    deps = dependencies or create_stock_analysis_workflow_dependencies(db_path)
    warnings: list[str] = []

    # Load configuration
    swing_policy = load_swing_policy_config()
    backtest_config = load_swing_backtest_config()

    # Build policy DTO
    policy = build_log_accumulation_trade_policy(swing_policy, backtest_config)

    # Build screen use case
    screen_uc = create_accumulation_screen_use_case(
        broker_repository=deps.broker_repository,
        market_repository=deps.market_repository,
        indicator_registry=deps.indicator_registry_factory(),
        rules_loader=deps.rules_loader_factory(),
        stockbit_providers=deps.stockbit_providers,
        signal_engine=deps.create_signal_engine(),
        ticker_profile_classifier_factory=deps.ticker_profile_classifier_factory,
        institutional_accumulation_config_factory=(deps.institutional_accumulation_config_factory),
        sector_context_builder_factory=deps.sector_context_builder_factory,
        sector_macro_context_builder_factory=deps.sector_macro_context_builder_factory,
        company_quality_context_builder_factory=(deps.company_quality_context_builder_factory),
    )

    # Build journal service
    journal_svc = AccumulationJournalService(
        store=AccumulationJournalCsvWriter(journal_path),
        repository=deps.market_repository,
    )

    # Handle regime engine context setup
    regime_uc = None
    if with_regime:
        try:
            cfg = load_app_config()
            regime_uc = create_market_context_engine(
                db_path=db_path,
                universe=regime_universe or cfg.analysis.regime_universe,
                benchmark=benchmark,
            )
        except Exception as exc:
            warnings.append(f"Warning: could not resolve regime universe: {exc}")

    # Build core candidate logger
    log_uc = LogSwingCandidateUseCase(
        screen_use_case=screen_uc,
        journal_service=journal_svc,
        market_repository=deps.market_repository,
        trade_journal_store=TradeJournalJsonlWriter(journal_path.parent / "trades.jsonl"),
        regime_use_case=regime_uc,
    )

    # Build final workflow orchestration use case
    workflow = LogAccumulationTradeWorkflowUseCase(
        log_use_case=log_uc,
        policy=policy,
        available_setups=AVAILABLE_SWING_SETUPS,
    )

    return LogAccumulationTradeWorkflowBundle(
        workflow=workflow,
        warnings=tuple(warnings),
    )


def create_accumulation_journal_service(
    *,
    db_path: Path,
    journal_path: Path,
) -> AccumulationJournalService:
    """Wire up repository and CSV store to build AccumulationJournalService."""
    market_repo = SQLiteMarketRepository(db_path=db_path)
    store = AccumulationJournalCsvWriter(journal_path)
    return AccumulationJournalService(store=store, repository=market_repo)
