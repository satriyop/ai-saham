"""Vertical RC-04 tests for the plan swing structure workflow."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.dto.plan_swing import (
    ScreenJudgmentStatus,
    ScreenJudgmentUnavailableReason,
)
from src.application.ports.rules_loader import RulesLoader
from src.application.use_case.plan_swing_workflow_use_case import (
    PlanSwingDataUnavailable,
    PlanSwingWorkflowUseCase,
)
from src.domain.value_objects.signal_assessment import (
    SWING_TRADE_SETUP_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)
from tests.application.use_case.plan_swing_workflow_fixtures import (
    FakeBrokerRepository,
    FakeMarketRepository,
    FakeRegistry,
    _candle,
    _fake_signal_evidence_context_builder,
    _request,
    _workflow,
)

SNAP = date(2026, 6, 18)


class _FakeRulesLoader(RulesLoader):
    def load(self, path=None, registry=None):
        raise NotImplementedError

    def load_from_string(self, content, registry=None, source_name="<generated>"):
        raise NotImplementedError


def _eval_result(candidate) -> SimpleNamespace:
    return SimpleNamespace(
        candidate=candidate,
        analysis_date=SNAP,
        consumed_candles=(),
        consumed_broker_summaries=(),
        consumed_broker_daily_flows=(),
    )


def _base_kwargs(market_repo, **overrides):
    kwargs = dict(
        market_repository=market_repo,
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: {},
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate_evaluation=lambda **kwargs: None,
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_policy_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        rules_loader=_FakeRulesLoader(),
        signal_evidence_context_builder=_fake_signal_evidence_context_builder(),
    )
    kwargs.update(overrides)
    return kwargs


class _MinimalCandidate:
    ticker = "BBCA"
    signal_assessment = None
    risk_assessment = None
    trade_setup = None
    accum_score = 10.0
    bandar_detector = None
    seasonal_edge = None
    analyst_consensus = None
    forward_estimates = None
    current_price = None
    insider_net_buy_ratio = None
    fundamentals = None
    shareholding = None
    foreign_flow_evidence = None
    ticker_notation = None
    consecutive_streak = 0
    trend = "SIDE"
    avg_flow_ratio = None
    vwap_discount_pct = None
    bb_width_pctile = None
    dividend_risk = False
    rights_issue_risk = False
    upcoming_rups = []
    insider_buying = False
    recent_insider_buys = []


def _signal_response(score: float) -> AssessSignalResponse:
    return AssessSignalResponse(
        ticker="BBCA",
        assessment=SignalAssessment(
            identity=SWING_TRADE_SETUP_IDENTITY,
            ticker="BBCA",
            snapshot_date=SNAP,
            score=score,
            strength=SignalStrength.STRONG,
            entry_quality=EntryQuality.ENTER,
            breakdown=(),
            rationale=(),
            signal_authority_coverage=None,
        ),
        coverage_warning=None,
    )


def test_no_candles_raises_data_unavailable() -> None:
    with pytest.raises(PlanSwingDataUnavailable):
        _workflow(FakeMarketRepository([]), []).execute(_request())


def test_accumulation_operational_failure_is_warning_and_no_candidate() -> None:
    def fail(**kwargs):
        raise RuntimeError("no broker rows")

    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(SNAP)]),
            build_accumulation_candidate_evaluation=fail,
        )
    )
    response = workflow.execute(_request())
    assert "Accumulation unavailable: no broker rows" in response.warnings
    assert response.judgment_ref.unavailable_reason is (
        ScreenJudgmentUnavailableReason.NO_SCREEN_CANDIDATE
    )


def test_candidate_without_signal_is_typed_unavailable() -> None:
    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(SNAP)]),
            build_accumulation_candidate_evaluation=lambda **kwargs: _eval_result(
                _MinimalCandidate()
            ),
        )
    )
    response = workflow.execute(_request())
    assert response.trade_setup is None
    assert response.judgment_ref.status is ScreenJudgmentStatus.UNAVAILABLE
    assert response.judgment_ref.unavailable_reason is (
        ScreenJudgmentUnavailableReason.NO_SCREEN_SIGNAL_ASSESSMENT
    )


def test_successful_later_plan_risk_cannot_fill_missing_screen_setup() -> None:
    """Vertical reproducer for the removed plan-owned Action fallback."""

    candidate = _MinimalCandidate()
    candidate.signal_assessment = _signal_response(40.0)
    candidate.risk_assessment = SimpleNamespace(to_dict=lambda: {"status": "OPEN"})
    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(SNAP)]),
            build_accumulation_candidate_evaluation=lambda **kwargs: _eval_result(candidate),
        )
    )

    response = workflow.execute(_request(capital=10_000_000))

    assert response.signal_assessment is candidate.signal_assessment
    assert response.trade_setup is None
    assert response.judgment_ref.unavailable_reason is (
        ScreenJudgmentUnavailableReason.NO_SCREEN_TRADE_SETUP
    )
    assert response.to_dict()["verdict"]["action"] is None


class _PassingSetupEval:
    passed = True
    name = "foreign-bounce"
    match = SimpleNamespace(value="MATCH")
    failed_reasons = ()


def test_setup_sizing_uses_explicit_entry_price() -> None:
    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(SNAP)]),
            evaluate_setup=lambda candidate, broker_detail: _PassingSetupEval(),
            resolve_setup_targets=lambda regime, config: (Decimal("6"), Decimal("3")),
        )
    )
    response = workflow.execute(
        _request(setup_name="foreign-bounce", capital=10_000_000, entry_price=1234.5)
    )
    assert response.setup_sizing is not None
    assert response.setup_sizing.entry_price == Decimal("1234.5")


def test_modules_have_no_plan_judgment_switches() -> None:
    workflow = PlanSwingWorkflowUseCase(**_base_kwargs(FakeMarketRepository([_candle(SNAP)])))
    response = workflow.execute(
        _request(
            setup_name="foreign-bounce",
            capital=10_000_000,
            strategy_name="does-not-exist",
            include_sentiment=True,
            include_flow_detail=True,
            include_signal_detail=True,
        )
    )
    assert response.modules == {
        "setup": True,
        "sizing": True,
        "strategy": True,
        "sentiment": True,
        "flow_detail": True,
        "signal_detail": True,
    }
