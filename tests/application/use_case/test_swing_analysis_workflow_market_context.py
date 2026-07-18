from datetime import date
from decimal import Decimal

from src.application.services.volatility_context import build_volatility_context
from src.application.use_case.swing_analysis_workflow_use_case import SwingAnalysisWorkflowUseCase
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from tests.application.use_case.swing_analysis_workflow_fixtures import (
    FakeBrokerRepository,
    FakeMarketRepository,
    FakeRegistry,
    _candle,
    _fake_signal_evidence_context_builder,
    _request,
    _workflow,
)


def test_swing_workflow_diagnostics_volatility_context_matches_shared_helper():
    workflow = SwingAnalysisWorkflowUseCase(
        market_repository=FakeMarketRepository([_candle(date(2026, 6, 18))]),
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
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        rules_loader=RulesYamlLoader(),
        signal_evidence_context_builder=_fake_signal_evidence_context_builder(),
    )

    response = workflow.execute(_request(auto_refresh=False))

    assert response.atr_value == Decimal("25")
    assert response.latest_close == Decimal("1010")

    expected_vc = build_volatility_context(
        atr_value=response.atr_value, latest_close=response.latest_close
    )

    payload = response.to_dict()
    volatility_context = payload["diagnostics"]["volatility_context"]

    assert set(volatility_context.keys()) == {
        "atr_20",
        "atr_pct",
        "volatility_bucket",
        "stop_model_hint",
        "suggested_stop_atr",
        "suggested_target_atr",
        "volatility_size_multiplier",
    }
    assert volatility_context["atr_20"] == expected_vc.atr_at_signal == 25.0
    assert volatility_context["atr_pct"] == expected_vc.atr_pct_at_signal == 2.4752
    assert (
        volatility_context["volatility_bucket"]
        == expected_vc.volatility_bucket_at_signal
        == "NORMAL"
    )
    assert volatility_context["stop_model_hint"] == "ATR_MULTIPLE"
    assert volatility_context["suggested_stop_atr"] == 2.0
    assert volatility_context["suggested_target_atr"] == 3.0
    assert (
        volatility_context["volatility_size_multiplier"]
        == expected_vc.volatility_size_multiplier_at_signal
        == 1.0
    )


def test_swing_workflow_preview_fields_are_none_without_market_context():
    workflow = _workflow(
        FakeMarketRepository([_candle(date(2026, 6, 18))]),
        [],
    )

    response = workflow.execute(_request(with_market_context=False))

    assert response.verdict is not None
    assert response.verdict.market_regime is None
    assert response.verdict.market_context_signal_preview is None
    assert response.verdict.market_context_risk_preview is None
    assert response.verdict.market_context_trade_setup_preview is None
    assert response.modules["market_context"] is False


def test_swing_workflow_mce_regime_forwarded_to_signal_engine():
    from src.application.use_case.assess_signal_use_case import AssessSignalResponse
    from src.domain.value_objects.market_context import MarketContext, MarketRegime
    from src.domain.value_objects.signal_assessment import (
        EntryQuality,
        SignalAssessment,
        SignalStrength,
    )

    _RISK_OFF_CONTEXT = MarketContext(
        regime=MarketRegime.RISK_OFF,
        conviction=0.9,
        factors=(),
        signal_multiplier=0.4,
        gate_tightening=True,
        as_of_date=date(2026, 6, 18),
        staleness_warning=None,
        coverage_warning=None,
    )
    _RAW_SIGNAL = SignalAssessment(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 18),
        score=75.0,
        strength=SignalStrength.STRONG,
        entry_quality=EntryQuality.ENTER,
        breakdown=(("bandar_intensity", 80.0), ("foreign_flow_quality", 70.0)),
        rationale=("bandar supportive",),
        signal_authority_coverage=None,
    )

    def _raw_signal_response():
        return AssessSignalResponse(
            ticker="BBCA",
            assessment=_RAW_SIGNAL,
            coverage_warning=None,
        )

    class FakeSignalEngine:
        received_market_contexts: list = []

        def evaluate(self, ticker, as_of_date=None, market_context=None):
            self.received_market_contexts.append(("evaluate", market_context))
            return _raw_signal_response()

        def evaluate_with_context(self, ticker, signal_context, market_context=None, **kwargs):
            self.received_market_contexts.append(("evaluate_with_context", market_context))
            return _raw_signal_response()

        def apply_market_context(self, response, market_context):
            return response

    class FakeRiskEngine:
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

    fake_signal = FakeSignalEngine()
    workflow = SwingAnalysisWorkflowUseCase(
        market_repository=FakeMarketRepository([_candle(date(2026, 6, 18))]),
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: {"freshness": "ok"},
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate_evaluation=lambda **kwargs: None,
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        rules_loader=RulesYamlLoader(),
        signal_evidence_context_builder=_fake_signal_evidence_context_builder(),
        evaluate_market_context=lambda **kwargs: _RISK_OFF_CONTEXT,
        signal_engine=fake_signal,
        risk_engine=FakeRiskEngine(),
    )

    fake_signal.received_market_contexts.clear()
    response_without_mce = workflow.execute(_request(with_market_context=False))
    assert response_without_mce.market_regime is None
    assert all(ctx is None for (_, ctx) in fake_signal.received_market_contexts), (
        "no market_context should be passed to signal engine when MCE disabled"
    )

    fake_signal.received_market_contexts.clear()
    response_with_mce = workflow.execute(_request(with_market_context=True))
    assert response_with_mce.market_regime is not None
    assert any(ctx is not None for (_, ctx) in fake_signal.received_market_contexts), (
        "market_context must be forwarded to signal engine when MCE enabled (ADR-037)"
    )

    assert response_with_mce.market_context_trade_setup_preview is not None
    assert response_with_mce.market_context_signal_preview is not None
    assert response_with_mce.verdict is not None
    assert (
        response_with_mce.verdict.market_context_trade_setup_preview
        is response_with_mce.market_context_trade_setup_preview
    )
