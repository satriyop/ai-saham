"""
Dependency and composition wiring for the saham plan swing workflow.

Layer: Adapter

Owns concrete construction of corporate-action risk assessment, the
indicator registry, structural/execution gates, the broker-detail builder
callable, and the setup evaluator callable, so the top-level workflow
factory can stay a thin assembly function.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.adapters.composition.stock_analysis_workflow_dependencies import (
    StockAnalysisWorkflowDependencies,
)
from src.application.dto.swing_config import SwingConfig
from src.application.services.swing_broker_detail_builder import build_broker_detail
from src.application.services.swing_setup_catalog import build_swing_setup_catalog_config
from src.application.use_case.assess_corporate_action_event_risk_use_case import (
    AssessCorporateActionEventRiskUseCase,
)
from src.application.use_case.evaluate_swing_setup_use_case import (
    EvaluateSwingSetupRequest,
    EvaluateSwingSetupUseCase,
)
from src.domain.rules.bandar_gate import BandarGate
from src.domain.rules.free_float_gate import FreeFloatGate
from src.domain.rules.fundamental_gate import FundamentalGate
from src.domain.rules.liquidity_gate import LiquidityGate
from src.infrastructure.config.corporate_action_policy_config import (
    load_corporate_action_policy_config,
)
from src.infrastructure.persistence.sqlite_corporate_action_calendar_repository import (
    SQLiteCorporateActionCalendarRepository,
)


def create_corporate_action_risk_use_case(
    db_path: Path,
) -> AssessCorporateActionEventRiskUseCase:
    return AssessCorporateActionEventRiskUseCase(
        repository=SQLiteCorporateActionCalendarRepository(db_path),
        policy=load_corporate_action_policy_config(),
    )


def create_workflow_registry(
    deps: StockAnalysisWorkflowDependencies,
):
    return deps.indicator_registry_factory(
        broker_repository=deps.broker_repository,
        market_repository=deps.market_repository,
    )


def create_structural_gates():
    return [FundamentalGate(), LiquidityGate(), FreeFloatGate()]


def create_execution_gates():
    return [BandarGate()]


def create_broker_detail_builder(
    *,
    smart_money_brokers: set[str],
    noise_brokers: set[str],
    broker_weights: dict[str, Decimal],
    swing_config: SwingConfig,
):
    def _build_broker_detail(ticker, broker_repo, window_sessions=5, as_of_date=None):
        return build_broker_detail(
            ticker=ticker,
            broker_repo=broker_repo,
            window_sessions=window_sessions,
            as_of_date=as_of_date,
            smart_money_brokers=smart_money_brokers,
            noise_brokers=noise_brokers,
            broker_weights=broker_weights,
            smart_share_threshold_pct=swing_config.smart_share_threshold_pct,
        )

    return _build_broker_detail


def create_setup_evaluator(
    *,
    setup_name: str | None,
    swing_config: SwingConfig,
):
    config = build_swing_setup_catalog_config(swing_config)

    def _evaluate_swing_setup(candidate, broker_detail=None):
        return EvaluateSwingSetupUseCase().execute(
            EvaluateSwingSetupRequest(
                setup_name=setup_name or "foreign-bounce",
                candidate=candidate,
                config=config,
                broker_detail=broker_detail,
            )
        )

    return _evaluate_swing_setup
