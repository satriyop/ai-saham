"""Unit tests for LogAccumulationTradeWorkflowUseCase."""

from datetime import date
from decimal import Decimal

import pytest

from src.application.dto.swing_policy_config import SetupTargetConfig, SwingPolicyConfig
from src.application.use_case.evaluate_swing_setup_use_case import SwingSetupCatalogConfig
from src.application.use_case.log_accumulation_trade_workflow_use_case import (
    LogAccumulationTradePolicy,
    LogAccumulationTradeWorkflowRequest,
    LogAccumulationTradeWorkflowUseCase,
    build_log_accumulation_trade_policy,
)
from src.application.use_case.log_swing_candidate_use_case import (
    LogSwingCandidateResponse,
)


class FakeLogSwingCandidateUseCase:
    def __init__(self, response: LogSwingCandidateResponse):
        self.response = response
        self.recorded_request = None

    def execute(self, request):
        self.recorded_request = request
        return self.response


class MockSwingBacktestConfig:
    def __init__(self, take_profit_pct: float, stop_loss_pct: float, max_hold_days: int):
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.max_hold_days = max_hold_days


@pytest.fixture
def dummy_response():
    return LogSwingCandidateResponse(
        ticker="BBRI",
        written=True,
        setup_match="MATCH",
        pattern="pattern",
        regime="RISK_ON",
        entry_price=Decimal("5000"),
        planned_stop=Decimal("4750"),
        planned_target=Decimal("5250"),
        failed_gates=(),
        candidate_accum_score=75.0,
    )


def test_build_log_accumulation_trade_policy_resolves_from_default_setup_target():
    swing_policy = SwingPolicyConfig(
        setup_targets={
            "default": SetupTargetConfig(take_profit_pct=Decimal("8"), stop_loss_pct=Decimal("4"))
        }
    )
    backtest_config = MockSwingBacktestConfig(
        take_profit_pct=5.0, stop_loss_pct=5.0, max_hold_days=10
    )
    policy = build_log_accumulation_trade_policy(swing_policy, backtest_config)
    assert policy.take_profit_pct == Decimal("8")
    assert policy.stop_loss_pct == Decimal("4")
    assert policy.max_hold_days == 10


def test_build_log_accumulation_trade_policy_falls_back_to_backtest():
    swing_policy = SwingPolicyConfig(setup_targets={})
    backtest_config = MockSwingBacktestConfig(
        take_profit_pct=5.5, stop_loss_pct=6.5, max_hold_days=12
    )
    policy = build_log_accumulation_trade_policy(swing_policy, backtest_config)
    assert policy.take_profit_pct == Decimal("5.5")
    assert policy.stop_loss_pct == Decimal("6.5")
    assert policy.max_hold_days == 12


def test_workflow_execution_builds_request_and_uppercases_and_lowercases(dummy_response):
    log_use_case = FakeLogSwingCandidateUseCase(dummy_response)
    policy = LogAccumulationTradePolicy(
        tier1_broker_codes=frozenset({"AK", "BK"}),
        setup_config=SwingSetupCatalogConfig(),
        resistance_gate_enabled=True,
        resistance_headroom_min_pct=5.0,
        ex_date_warning_days=10,
        take_profit_pct=Decimal("8"),
        stop_loss_pct=Decimal("4"),
        max_hold_days=10,
    )

    workflow = LogAccumulationTradeWorkflowUseCase(
        log_use_case=log_use_case,
        policy=policy,
        available_setups=("foreign-bounce", "coiled-spring"),
    )

    request = LogAccumulationTradeWorkflowRequest(
        ticker="bbri",
        window=7,
        entry_price=Decimal("5000"),
        from_analysis=True,
        setup="FOREIGN-BOUNCE",
        with_regime=True,
        benchmark="IHSG",
        logged_at=date(2026, 1, 1),
    )

    result = workflow.execute(request)

    assert result.setup_name == "foreign-bounce"
    assert result.logged_at == date(2026, 1, 1)
    assert result.max_hold_days == 10

    recorded = log_use_case.recorded_request
    assert recorded is not None
    assert recorded.ticker == "BBRI"
    assert recorded.window_days == 7
    assert recorded.entry_price == Decimal("5000")
    assert recorded.from_analysis is True
    assert recorded.setup == "foreign-bounce"
    assert recorded.with_regime is True
    assert recorded.regime_universe == []
    assert recorded.benchmark_ticker == "IHSG"
    assert recorded.logged_at == date(2026, 1, 1)
    assert recorded.tier1_broker_codes == policy.tier1_broker_codes
    assert recorded.setup_config == policy.setup_config
    assert recorded.resistance_gate_enabled == policy.resistance_gate_enabled
    assert recorded.resistance_headroom_min_pct == policy.resistance_headroom_min_pct
    assert recorded.ex_date_warning_days == policy.ex_date_warning_days
    assert recorded.take_profit_pct == policy.take_profit_pct
    assert recorded.stop_loss_pct == policy.stop_loss_pct
    assert recorded.max_hold_days == policy.max_hold_days


def test_workflow_execution_rejects_unknown_setup_when_from_analysis_is_true(dummy_response):
    log_use_case = FakeLogSwingCandidateUseCase(dummy_response)
    policy = LogAccumulationTradePolicy(
        tier1_broker_codes=frozenset(),
        setup_config=SwingSetupCatalogConfig(),
        resistance_gate_enabled=True,
        resistance_headroom_min_pct=5.0,
        ex_date_warning_days=10,
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
        max_hold_days=10,
    )
    workflow = LogAccumulationTradeWorkflowUseCase(
        log_use_case=log_use_case,
        policy=policy,
        available_setups=("foreign-bounce",),
    )

    request = LogAccumulationTradeWorkflowRequest(
        ticker="BBRI",
        window=7,
        entry_price=Decimal("5000"),
        from_analysis=True,
        setup="unknown-setup",
        with_regime=True,
        benchmark="IHSG",
        logged_at=date(2026, 1, 1),
    )

    with pytest.raises(ValueError) as excinfo:
        workflow.execute(request)

    assert "Unknown swing setup 'unknown-setup'. Available setups: foreign-bounce" in str(
        excinfo.value
    )


def test_workflow_execution_allows_unknown_setup_when_from_analysis_is_false(dummy_response):
    log_use_case = FakeLogSwingCandidateUseCase(dummy_response)
    policy = LogAccumulationTradePolicy(
        tier1_broker_codes=frozenset(),
        setup_config=SwingSetupCatalogConfig(),
        resistance_gate_enabled=True,
        resistance_headroom_min_pct=5.0,
        ex_date_warning_days=10,
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
        max_hold_days=10,
    )
    workflow = LogAccumulationTradeWorkflowUseCase(
        log_use_case=log_use_case,
        policy=policy,
        available_setups=("foreign-bounce",),
    )

    request = LogAccumulationTradeWorkflowRequest(
        ticker="BBRI",
        window=7,
        entry_price=Decimal("5000"),
        from_analysis=False,
        setup="unknown-setup",
        with_regime=True,
        benchmark="IHSG",
        logged_at=date(2026, 1, 1),
    )

    result = workflow.execute(request)
    assert result.setup_name == "unknown-setup"
    assert result.max_hold_days == 10

    recorded = log_use_case.recorded_request
    assert recorded is not None
    assert recorded.setup is None
