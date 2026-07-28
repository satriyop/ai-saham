"""Characterization tests for the split PlanSwingWorkflowUseCase pipeline.

Layer: Application (test)

Locks in behavior that must survive the collaborator extraction
(input collector, decision composer, optional evidence runner, sizing
service, response assembler): warning text, response field wiring, and
module flags.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.dto.assess_signal import AssessSignalResponse
from src.application.ports.rules_loader import RulesLoader
from src.application.use_case.plan_swing_workflow_use_case import (
    PlanSwingDataUnavailable,
    PlanSwingWorkflowUseCase,
)
from src.domain.value_objects.market_context import MarketContext, MarketRegime
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


class _FakeRulesLoader(RulesLoader):
    """Minimal RulesLoader stand-in — these tests never parse real YAML."""

    def load(self, path=None, registry=None):
        raise NotImplementedError("not exercised by these tests")

    def load_from_string(self, content, registry=None, source_name="<generated>"):
        raise NotImplementedError("not exercised by these tests")


def _eval_result(candidate) -> SimpleNamespace:
    """Minimal stand-in for AccumulationCandidateEvaluationResult."""
    return SimpleNamespace(
        candidate=candidate,
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


def test_no_candles_raises_data_unavailable():
    workflow = _workflow(FakeMarketRepository([]), [])

    with pytest.raises(PlanSwingDataUnavailable):
        workflow.execute(_request())


def test_accumulation_build_failure_returns_exact_warning():
    def build_accumulation_candidate_evaluation(**kwargs):
        raise RuntimeError("no broker rows")

    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(date(2026, 6, 18))]),
            build_accumulation_candidate_evaluation=build_accumulation_candidate_evaluation,
        )
    )

    response = workflow.execute(_request())

    assert "Accumulation unavailable: no broker rows" in response.warnings


def test_market_context_failure_returns_exact_warning():
    def evaluate_market_context(**kwargs):
        raise RuntimeError("regime boom")

    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(date(2026, 6, 18))]),
            evaluate_market_context=evaluate_market_context,
        )
    )

    response = workflow.execute(_request(with_market_context=True))

    assert "Market regime unavailable: regime boom" in response.warnings


class _MinimalCandidate:
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
    signal_assessment = None


def _signal_response(score: float) -> AssessSignalResponse:
    return AssessSignalResponse(
        ticker="BBCA",
        assessment=SignalAssessment(
            identity=SWING_TRADE_SETUP_IDENTITY,
            ticker="BBCA",
            snapshot_date=date(2026, 6, 18),
            score=score,
            strength=SignalStrength.STRONG,
            entry_quality=EntryQuality.ENTER,
            breakdown=(),
            rationale=(),
            signal_authority_coverage=None,
        ),
        coverage_warning=None,
    )


def test_signal_assessment_failure_returns_exact_warning():
    class FailingSignalEngine:
        def foreign_flow_quality_from_accum_score(self, score):
            return None

        def bandar_max_range(self, n):
            return 0

        def evaluate_swing_trade_setup(self, ticker, signal_context, market_context=None, **kwargs):
            raise RuntimeError("signal boom")

    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(date(2026, 6, 18))]),
            build_accumulation_candidate_evaluation=lambda **kwargs: _eval_result(
                _MinimalCandidate()
            ),
            signal_engine=FailingSignalEngine(),
        )
    )

    # Re-score path only runs with explicit re-judge flags (ADR-054 S3).
    response = workflow.execute(_request(with_market_context=True))

    assert "Evidence-enriched signal re-score unavailable: signal boom" in response.warnings


class _RescoreSignalEngine:
    """Fast-path candidate signal, then rescore on evidence-enriched call."""

    def __init__(self, *, fail_rescore: bool = False) -> None:
        self.rescore_calls = 0
        self._fail_rescore = fail_rescore

    def foreign_flow_quality_from_accum_score(self, score):
        return None

    def bandar_max_range(self, n):
        return 0

    def evaluate(self, ticker, as_of_date=None, market_context=None):
        # Exist solely as an explicit regression trap. Standalone evaluate should not run when
        # candidate present.
        raise AssertionError("standalone evaluate should not run when candidate present")

    def evaluate_swing_trade_setup(self, ticker, signal_context, market_context=None, **kwargs):
        self.rescore_calls += 1
        if self._fail_rescore:
            raise RuntimeError("rescore boom")
        return _signal_response(90.0)

    def apply_market_context(self, response, market_context):
        return response


class _FakeRiskEngine:
    def _make_response(self):
        from src.application.use_case.assess_risk_use_case import AssessRiskResponse
        from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
        from src.domain.value_objects.risk_assessment import RiskAssessment

        assessment = RiskAssessment(
            gate_triggered=None,
            gate_is_structural=None,
            rationale=(),
            snapshot_date=date(2026, 6, 18),
            indicators=IndicatorSnapshot(
                date=date(2026, 6, 18),
                sma=Decimal("1000"),
                ema=Decimal("1005"),
                rsi=Decimal("50"),
            ),
        )
        return AssessRiskResponse(
            ticker="BBCA",
            assessment=assessment,
            sma_period=20,
            ema_period=20,
            rsi_period=14,
        )

    def assess_with_context(self, ticker, gate_context, market_context=None):
        return self._make_response()

    def assess(self, ticker, as_of_date=None, market_context=None):
        return self._make_response()

    def apply_market_context(self, response, market_context):
        from src.application.services.risk_engine import _apply_regime_gate

        return _apply_regime_gate(response, market_context)


_MARKET_CONTEXT = MarketContext(
    regime=MarketRegime.RISK_ON,
    conviction=0.9,
    factors=(),
    signal_multiplier=1.0,
    gate_tightening=False,
    as_of_date=date(2026, 6, 18),
    staleness_warning=None,
    coverage_warning=None,
)


def test_evidence_enriched_rescore_failure_returns_exact_warning():
    signal_engine = _RescoreSignalEngine(fail_rescore=True)
    # Fast path: candidate already carries a pre-computed signal_assessment,
    # so the initial signal step reuses it without calling evaluate_swing_trade_setup.
    candidate = _MinimalCandidate()
    candidate.signal_assessment = _signal_response(40.0)

    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(date(2026, 6, 18))]),
            build_accumulation_candidate_evaluation=lambda **kwargs: _eval_result(candidate),
            signal_engine=signal_engine,
            risk_engine=_FakeRiskEngine(),
        )
    )

    # Re-score path only runs with explicit re-judge flags (ADR-054 S3).
    response = workflow.execute(_request(with_market_context=True))

    assert signal_engine.rescore_calls == 1
    assert "Evidence-enriched signal re-score unavailable: rescore boom" in response.warnings
    # Under the new availability-aware design, a failed rescore clears the signal assessment
    assert response.signal_assessment is None
    from src.application.dto.plan_swing import (
        SignalAssessmentStatus,
        SignalAssessmentUnavailableReason,
    )

    assert response.signal_assessment_availability.status == SignalAssessmentStatus.UNAVAILABLE
    assert (
        response.signal_assessment_availability.unavailable_reason
        == SignalAssessmentUnavailableReason.ASSESSMENT_FAILED
    )
    assert response.verdict.signal_assessment is None
    assert response.trade_setup is None
    assert response.market_context_signal_preview is None
    assert response.market_context_trade_setup_preview is None
    assert response.verdict.trade_setup is None
    assert response.verdict.market_context_signal_preview is None
    assert response.verdict.market_context_trade_setup_preview is None


def test_evidence_enriched_rescore_success_updates_response():
    signal_engine = _RescoreSignalEngine(fail_rescore=False)
    candidate = _MinimalCandidate()
    candidate.signal_assessment = _signal_response(40.0)

    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(date(2026, 6, 18))]),
            build_accumulation_candidate_evaluation=lambda **kwargs: _eval_result(candidate),
            signal_engine=signal_engine,
            risk_engine=_FakeRiskEngine(),
            evaluate_market_context=lambda **kwargs: _MARKET_CONTEXT,
        )
    )

    response = workflow.execute(_request(with_market_context=True))

    assert signal_engine.rescore_calls == 1
    assert response.signal_assessment.assessment.score == 90.0
    assert response.trade_setup is not None
    assert response.verdict.signal_assessment.assessment.score == 90.0
    assert response.verdict.trade_setup is response.trade_setup
    assert response.market_context_signal_preview.assessment.score == 90.0
    assert response.market_context_trade_setup_preview is not None
    assert response.verdict.market_context_trade_setup_preview is (
        response.market_context_trade_setup_preview
    )


class _SignalEngineMustNotAssessWithoutEvidence:
    def __init__(self) -> None:
        self.evaluate_swing_trade_setup_calls = 0

    def evaluate_swing_trade_setup(self, *args, **kwargs):
        self.evaluate_swing_trade_setup_calls += 1
        raise AssertionError("SignalEngine must not assess when no candidate evidence exists")


def test_no_candidate_reports_typed_unavailable_without_signal_assessment():
    signal_engine = _SignalEngineMustNotAssessWithoutEvidence()

    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(date(2026, 6, 18))]),
            build_accumulation_candidate_evaluation=lambda **kwargs: None,
            signal_engine=signal_engine,
        )
    )

    response = workflow.execute(_request())

    assert signal_engine.evaluate_swing_trade_setup_calls == 0

    from src.application.dto.plan_swing import (
        SignalAssessmentStatus,
        SignalAssessmentUnavailableReason,
    )

    assert response.signal_assessment_availability.status is (SignalAssessmentStatus.UNAVAILABLE)
    assert response.signal_assessment_availability.unavailable_reason is (
        SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE
    )

    assert response.signal_assessment is None
    assert response.trade_setup is None
    assert response.market_context_signal_preview is None
    assert response.market_context_trade_setup_preview is None

    assert response.verdict.signal_assessment is None
    assert response.verdict.trade_setup is None
    assert response.verdict.market_context_signal_preview is None
    assert response.verdict.market_context_trade_setup_preview is None

    payload = response.to_dict()
    verdict_payload = payload["verdict"]

    assert verdict_payload["signal_assessment_status"] == "UNAVAILABLE"
    assert (
        verdict_payload["signal_assessment_unavailable_reason"] == "no_production_signal_evidence"
    )
    assert verdict_payload["signal_assessment"] is None
    assert verdict_payload["trade_setup"] is None


class _PassingSetupEval:
    passed = True
    name = "foreign-bounce"


def test_setup_sizing_uses_explicit_entry_price():
    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(date(2026, 6, 18))]),
            evaluate_setup=lambda candidate, broker_detail: _PassingSetupEval(),
            resolve_setup_targets=lambda regime, config: (Decimal("6"), Decimal("3")),
        )
    )

    response = workflow.execute(
        _request(setup_name="foreign-bounce", capital=10_000_000, entry_price=1234.5)
    )

    assert response.setup_sizing is not None
    assert response.setup_sizing.entry_price == Decimal("1234.5")


def test_module_flags_unchanged_for_all_toggles_enabled():
    workflow = PlanSwingWorkflowUseCase(
        **_base_kwargs(
            FakeMarketRepository([_candle(date(2026, 6, 18))]),
            build_flow_detail=lambda **kwargs: {"flow": True},
            build_broker_detail=lambda **kwargs: {"broker": True},
            fetch_sentiment=lambda **kwargs: (None, "no sentiment"),
            evaluate_market_context=lambda **kwargs: None,
        )
    )

    request = _request(
        setup_name="foreign-bounce",
        capital=10_000_000,
        strategy_name="does-not-exist",
        include_sentiment=True,
        include_flow_detail=True,
        include_signal_detail=True,
        include_risk_detail=True,
        include_market_detail=True,
        with_market_context=True,
        with_technical_gate=True,
    )

    response = workflow.execute(request)

    assert response.modules == {
        "setup": True,
        "sizing": True,
        "strategy": True,
        "sentiment": True,
        "flow_detail": True,
        "signal_detail": True,
        "risk_detail": True,
        "market_detail": True,
        "market_context": True,
        "technical_gate": True,
    }
