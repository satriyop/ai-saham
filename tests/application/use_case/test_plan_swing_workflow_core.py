from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.services.plan_swing_market_helpers import simple_return
from src.application.use_case.plan_swing_workflow_use_case import (
    PlanSwingDataUnavailable,
    PlanSwingWorkflowUseCase,
)
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from tests.application.use_case.plan_swing_workflow_fixtures import (
    FakeBrokerRepository,
    FakeMarketRepository,
    FakeRegistry,
    _candle,
    _candle_with_close,
    _fake_signal_evidence_context_builder,
    _request,
    _workflow,
)


def test_simple_return_computes_decimal_return_from_candles():
    start = date(2026, 6, 1)
    candles = [
        _candle_with_close(start + timedelta(days=idx), str(1000 + (idx * 10))) for idx in range(20)
    ]

    ret = simple_return(candles, lookback=20, min_valid=18)

    assert ret == pytest.approx(0.19)


def test_swing_workflow_runs_without_auto_refresh():
    calls: list[str] = []
    workflow = _workflow(
        FakeMarketRepository([_candle(date(2026, 6, 18))]),
        calls,
    )

    response = workflow.execute(_request(auto_refresh=False))

    assert calls == []
    assert response.refresh_actions == ("disabled",)
    assert response.latest_close == Decimal("1010")
    assert response.atr_value == Decimal("25")
    assert response.modules["strategy"] is False
    assert response.modules["sentiment"] is False
    assert response.modules["flow_detail"] is False
    assert response.verdict is not None
    assert response.evidence is not None
    assert response.diagnostics is not None
    assert response.diagnostics.data_freshness == {"freshness": ("disabled",)}
    assert response.diagnostics.flow_detail is None
    assert response.diagnostics.broker_detail is None
    assert response.verdict.trade_setup is None
    assert response.evidence.accumulation_candidate is response.accumulation_candidate
    assert response.evidence.accumulation_candidate.ticker == "BBCA"


def test_swing_workflow_raises_when_candles_are_missing():
    workflow = _workflow(FakeMarketRepository([]), [])

    with pytest.raises(PlanSwingDataUnavailable):
        workflow.execute(_request())


def test_swing_workflow_records_accumulation_failure_warning():
    def build_accumulation_candidate_evaluation(**kwargs):
        raise RuntimeError("no broker rows")

    workflow = PlanSwingWorkflowUseCase(
        market_repository=FakeMarketRepository([_candle(date(2026, 6, 18))]),
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: ("candles=ok",),
        build_data_freshness=lambda **kwargs: None,
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate_evaluation=build_accumulation_candidate_evaluation,
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_policy_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        rules_loader=RulesYamlLoader(),
        signal_evidence_context_builder=_fake_signal_evidence_context_builder(),
    )

    response = workflow.execute(_request())

    assert response.evidence is not None
    assert response.evidence.accumulation_candidate is None
    assert "Accumulation unavailable: no broker rows" in response.warnings
