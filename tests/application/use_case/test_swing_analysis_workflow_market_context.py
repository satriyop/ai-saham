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


# test_swing_workflow_mce_regime_forwarded_to_signal_engine removed and moved to
# test_swing_analysis_decision_composer.py
