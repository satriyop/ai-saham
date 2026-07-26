"""Focused tests for the analyze_swing_workflow_factory contextual split.

Layer: Test (adapter composition split guard).
"""

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.adapters.cli.analyze_swing_workflow_factory import create_swing_analysis_workflow
from src.adapters.composition.stock_analysis_workflow_dependencies import (
    StockAnalysisWorkflowDependencies,
)
from src.domain.ports.broker_data_repository import BrokerDataRepository
from src.domain.ports.market_data_repository import MarketDataRepository
from src.infrastructure.browser.stockbit_providers import StockbitProviders
from src.infrastructure.persistence.sqlite_candidate_observations_repository import (
    SQLiteCandidateObservationsRepository,
)

FACTORY_PATH = Path("src/adapters/cli/analyze_swing_workflow_factory.py")

FORBIDDEN_IMPORT_NAMES = {
    "SentimentFactory",
    "create_accumulation_screen_use_case",
    "SQLiteCorporateActionCalendarRepository",
    "load_corporate_action_policy_config",
    "FundamentalGate",
    "LiquidityGate",
    "FreeFloatGate",
    "BandarGate",
}

FORBIDDEN_FUNCTION_DEFS = {
    "_build_accumulation_candidate",
    "_build_broker_detail",
    "_auto_refresh_swing_data",
    "_setup_config",
    "_evaluate_swing_setup",
    "_quiet_sentiment_fetch",
    "_fetch_swing_sentiment",
}


def _factory_tree() -> ast.Module:
    return ast.parse(FACTORY_PATH.read_text(encoding="utf-8"))


def _imported_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _defined_function_names(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _fake_dependencies(tmp_path) -> StockAnalysisWorkflowDependencies:
    fake_registry = MagicMock()
    fake_rules_loader = MagicMock()
    return StockAnalysisWorkflowDependencies(
        db_path=tmp_path / "test.db",
        broker_repository=MagicMock(spec=BrokerDataRepository),
        market_repository=MagicMock(spec=MarketDataRepository),
        candidate_observations_repository=MagicMock(spec=SQLiteCandidateObservationsRepository),
        observation_risk_assessment_repository=MagicMock(),
        stockbit_providers=MagicMock(spec=StockbitProviders),
        rules_loader_factory=lambda: fake_rules_loader,
        indicator_registry_factory=lambda *args, **kwargs: fake_registry,
        ticker_profile_classifier_factory=lambda: MagicMock(),
        institutional_accumulation_config_factory=lambda: MagicMock(),
        sector_context_builder_factory=lambda: MagicMock(),
        company_quality_context_builder_factory=lambda: MagicMock(),
        create_risk_engine=lambda: MagicMock(),
        create_signal_engine=lambda: MagicMock(),
        create_market_context_provider=MagicMock,
    )


def test_create_swing_analysis_workflow_accepts_fake_dependencies(tmp_path):
    fake_deps = _fake_dependencies(tmp_path)

    with patch(
        "src.adapters.cli.analyze_swing_workflow_factory.SwingAnalysisWorkflowUseCase"
    ) as mock_uc_class:
        create_swing_analysis_workflow(
            db_path=tmp_path / "test.db",
            setup_name="foreign-bounce",
            swing_config=MagicMock(),
            analyze_config=MagicMock(),
            smart_money_brokers=set(),
            noise_brokers=set(),
            broker_weights={},
            dependencies=fake_deps,
        )

    mock_uc_class.assert_called_once()


def test_workflow_receives_callable_build_accumulation_candidate_evaluation(tmp_path):
    fake_deps = _fake_dependencies(tmp_path)

    with patch(
        "src.adapters.cli.analyze_swing_workflow_factory.SwingAnalysisWorkflowUseCase"
    ) as mock_uc_class:
        create_swing_analysis_workflow(
            db_path=tmp_path / "test.db",
            setup_name="foreign-bounce",
            swing_config=MagicMock(),
            analyze_config=MagicMock(),
            smart_money_brokers=set(),
            noise_brokers=set(),
            broker_weights={},
            dependencies=fake_deps,
        )

    _args, kwargs = mock_uc_class.call_args
    assert callable(kwargs["build_accumulation_candidate_evaluation"])


def test_workflow_receives_callable_refresh_data(tmp_path):
    fake_deps = _fake_dependencies(tmp_path)

    with patch(
        "src.adapters.cli.analyze_swing_workflow_factory.SwingAnalysisWorkflowUseCase"
    ) as mock_uc_class:
        create_swing_analysis_workflow(
            db_path=tmp_path / "test.db",
            setup_name="foreign-bounce",
            swing_config=MagicMock(),
            analyze_config=MagicMock(),
            smart_money_brokers=set(),
            noise_brokers=set(),
            broker_weights={},
            dependencies=fake_deps,
        )

    _args, kwargs = mock_uc_class.call_args
    assert callable(kwargs["refresh_data"])


def test_workflow_receives_callable_fetch_sentiment(tmp_path):
    fake_deps = _fake_dependencies(tmp_path)

    with patch(
        "src.adapters.cli.analyze_swing_workflow_factory.SwingAnalysisWorkflowUseCase"
    ) as mock_uc_class:
        create_swing_analysis_workflow(
            db_path=tmp_path / "test.db",
            setup_name="foreign-bounce",
            swing_config=MagicMock(),
            analyze_config=MagicMock(),
            smart_money_brokers=set(),
            noise_brokers=set(),
            broker_weights={},
            dependencies=fake_deps,
        )

    _args, kwargs = mock_uc_class.call_args
    assert callable(kwargs["fetch_sentiment"])


def test_factory_does_not_import_forbidden_names():
    tree = _factory_tree()
    imported = _imported_names(tree)
    leaked = imported & FORBIDDEN_IMPORT_NAMES
    assert not leaked, f"analyze_swing_workflow_factory.py must not import: {leaked}"


def test_factory_does_not_define_old_private_helpers():
    tree = _factory_tree()
    defined = _defined_function_names(tree)
    leaked = defined & FORBIDDEN_FUNCTION_DEFS
    assert not leaked, f"analyze_swing_workflow_factory.py must not define: {leaked}"
