"""
Adapter composition root/factory for the log accumulation trade workflow.

Layer: Adapter
"""

from pathlib import Path
from typing import Optional

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
from src.infrastructure.browser.stockbit_provider_bundle import (
    create_readonly_stockbit_providers,
)
from src.infrastructure.composition.indicator_registry_factory import (
    create_indicator_registry,
)
from src.infrastructure.config.app_config import APP_CFG
from src.infrastructure.config.company_quality_context_config_loader import (
    create_company_quality_context_evidence_builder,
)
from src.infrastructure.config.institutional_accumulation_config_loader import (
    load_institutional_accumulation_config,
)
from src.infrastructure.config.market_context_factory import create_market_context_engine
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from src.infrastructure.config.sector_context_config_loader import (
    create_sector_context_evidence_builder,
)
from src.infrastructure.config.swing_backtest_config import load_swing_backtest_config
from src.infrastructure.config.swing_config import load_swing_config
from src.infrastructure.config.ticker_profile_config_loader import (
    create_ticker_profile_classifier,
)
from src.infrastructure.persistence.accumulation_journal_csv_writer import (
    AccumulationJournalCsvWriter,
)
from src.infrastructure.persistence.sqlite_broker_repository import SQLiteBrokerRepository
from src.infrastructure.persistence.sqlite_market_repository import SQLiteMarketRepository
from src.infrastructure.persistence.trade_journal_jsonl_writer import TradeJournalJsonlWriter


def create_log_accumulation_trade_workflow(
    *,
    db_path: Path,
    journal_path: Path,
    with_regime: bool,
    regime_universe: Optional[str],
    benchmark: str,
) -> LogAccumulationTradeWorkflowBundle:
    """Wire up all repository, service, and engine dependencies for log swing trade workflow."""
    warnings: list[str] = []

    # Load configuration
    swing_config = load_swing_config()
    backtest_config = load_swing_backtest_config()

    # Build policy DTO
    policy = build_log_accumulation_trade_policy(swing_config, backtest_config)

    # Instantiate repositories & providers
    broker_repo = SQLiteBrokerRepository(db_path)
    market_repo = SQLiteMarketRepository(db_path=db_path)
    sb = create_readonly_stockbit_providers(db_path)

    # Build screen use case
    screen_uc = create_accumulation_screen_use_case(
        broker_repository=broker_repo,
        market_repository=market_repo,
        indicator_registry=create_indicator_registry(),
        rules_loader=RulesYamlLoader(),
        stockbit_providers=sb,
        ticker_profile_classifier_factory=create_ticker_profile_classifier,
        institutional_accumulation_config_factory=load_institutional_accumulation_config,
        sector_context_builder_factory=create_sector_context_evidence_builder,
        company_quality_context_builder_factory=create_company_quality_context_evidence_builder,
    )

    # Build journal service
    journal_svc = AccumulationJournalService(
        store=AccumulationJournalCsvWriter(journal_path),
        repository=market_repo,
    )

    # Handle regime engine context setup
    regime_uc = None
    if with_regime:
        try:
            regime_uc = create_market_context_engine(
                db_path=db_path,
                universe=regime_universe or APP_CFG.analysis.regime_universe,
                benchmark=benchmark,
            )
        except Exception as exc:
            warnings.append(f"Warning: could not resolve regime universe: {exc}")

    # Build core candidate logger
    log_uc = LogSwingCandidateUseCase(
        screen_use_case=screen_uc,
        journal_service=journal_svc,
        market_repository=market_repo,
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
