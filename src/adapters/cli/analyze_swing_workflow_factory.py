"""
Factory for the saham analyze swing workflow.

Layer: Adapter

This module owns CLI/infrastructure wiring so analyze_swing_commands.py can stay
focused on flag parsing, request construction, execution, and rendering.

Dependency/candidate/fetcher composition lives in dedicated sibling modules:
analyze_swing_dependency_factory, analyze_swing_candidate_builder, and
analyze_swing_optional_fetchers.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.adapters.cli.analyze_swing_candidate_builder import (
    create_accumulation_candidate_builder,
)
from src.adapters.cli.analyze_swing_dependency_factory import (
    create_broker_detail_builder,
    create_corporate_action_risk_use_case,
    create_execution_gates,
    create_setup_evaluator,
    create_structural_gates,
    create_workflow_registry,
)
from src.adapters.cli.analyze_swing_optional_fetchers import (
    auto_refresh_swing_data,
    fetch_swing_sentiment,
)
from src.adapters.cli.stock_analysis_workflow_dependencies import (
    StockAnalysisWorkflowDependencies,
    create_stock_analysis_workflow_dependencies,
)
from src.application.dto.swing_config import SwingConfig
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSessionResolver,
)
from src.application.services.signal_evidence_execution_context_builder import (
    SignalEvidenceExecutionContextBuilder,
)
from src.infrastructure.persistence.ihsg_trading_session_calendar_provider import (
    IHSGTradingSessionCalendarProvider,
)
from src.application.services.swing_broker_detail_builder import (
    build_broker_quality_note,
    build_flow_detail,
)
from src.application.services.swing_data_freshness import build_swing_data_freshness
from src.application.use_case.accumulation_screen_use_case import resolve_setup_targets
from src.application.use_case.swing_analysis_workflow_use_case import SwingAnalysisWorkflowUseCase
from src.infrastructure.config.accumulation_screener_config import (
    load_accumulation_screener_config,
)
from src.infrastructure.config.analyze_swing_config import AnalyzeSwingConfig
from src.infrastructure.config.market_context_factory import evaluate_market_context


def create_swing_analysis_workflow(
    *,
    db_path: Path,
    setup_name: str | None,
    swing_config: SwingConfig,
    analyze_config: AnalyzeSwingConfig,
    smart_money_brokers: set[str],
    noise_brokers: set[str],
    broker_weights: dict[str, Decimal],
    dependencies: StockAnalysisWorkflowDependencies | None = None,
) -> SwingAnalysisWorkflowUseCase:
    """Build the composite swing analysis workflow with CLI infrastructure."""
    deps = dependencies or create_stock_analysis_workflow_dependencies(db_path)
    accumulation_config = load_accumulation_screener_config()

    build_accumulation_candidate_evaluation = create_accumulation_candidate_builder(
        deps=deps,
        swing_config=swing_config,
        analyze_config=analyze_config,
        accumulation_config=accumulation_config,
    )
    build_broker_detail = create_broker_detail_builder(
        smart_money_brokers=smart_money_brokers,
        noise_brokers=noise_brokers,
        broker_weights=broker_weights,
        swing_config=swing_config,
    )
    evaluate_setup = create_setup_evaluator(setup_name=setup_name, swing_config=swing_config)

    return SwingAnalysisWorkflowUseCase(
        market_repository=deps.market_repository,
        broker_repository=deps.broker_repository,
        registry=create_workflow_registry(deps),
        refresh_data=lambda ticker, db_path, force_refresh: auto_refresh_swing_data(
            ticker=ticker,
            db_path=db_path,
            force_refresh=force_refresh,
            analyze_config=analyze_config,
        ),
        build_data_freshness=build_swing_data_freshness,
        build_flow_detail=build_flow_detail,
        build_broker_detail=build_broker_detail,
        build_accumulation_candidate_evaluation=build_accumulation_candidate_evaluation,
        evaluate_setup=evaluate_setup,
        build_broker_quality_note=lambda broker_detail, setup_eval: build_broker_quality_note(
            broker_detail,
            setup_eval,
            smart_sell_min_share_pct=swing_config.smart_sell_min_share_pct,
        ),
        fetch_sentiment=lambda ticker, sentiment_verbose: fetch_swing_sentiment(
            ticker=ticker,
            sentiment_verbose=sentiment_verbose,
            analyze_config=analyze_config,
        ),
        load_swing_config=lambda: swing_config,
        resolve_setup_targets=resolve_setup_targets,
        rules_loader=deps.rules_loader_factory(),
        evaluate_market_context=evaluate_market_context,
        structural_gates=create_structural_gates(),
        execution_gates=create_execution_gates(),
        signal_engine=deps.create_signal_engine(),
        risk_engine=deps.create_risk_engine(),
        candidate_observations_repository=deps.candidate_observations_repository,
        foreign_flow_score_policy=accumulation_config.foreign_flow_score_policy,
        corporate_action_risk_use_case=create_corporate_action_risk_use_case(db_path),
        ticker_profile_classifier_factory=deps.ticker_profile_classifier_factory,
        institutional_accumulation_config_factory=(
            deps.institutional_accumulation_config_factory
        ),
        sector_context_builder_factory=deps.sector_context_builder_factory,
        company_quality_context_builder_factory=(
            deps.company_quality_context_builder_factory
        ),
        session_resolver=EffectiveMarketSessionResolver(deps.market_repository),
        signal_evidence_context_builder=SignalEvidenceExecutionContextBuilder(
            trading_session_calendar_loader=lambda start, end:
                IHSGTradingSessionCalendarProvider(
                    deps.market_repository
                ).load(
                    coverage_start=start,
                    coverage_end=end,
                )
        ),
    )
