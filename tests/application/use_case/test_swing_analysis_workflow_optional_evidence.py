from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.application.use_case.swing_analysis_workflow_use_case import SwingAnalysisWorkflowUseCase
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupGate, SetupMatch
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader
from tests.application.use_case.swing_analysis_workflow_fixtures import (
    FakeBrokerRepository,
    FakeLearningObservationsRepository,
    FakeMarketRepository,
    FakeRegistry,
    _breakout_candles,
    _candle,
    _fake_signal_evidence_context_builder,
    _request,
    _workflow,
)


def test_swing_analysis_workflow_can_emit_breakout_confirmation_with_local_volume_source():
    candidate = SimpleNamespace(
        ticker="BBCA",
        trend="SIDE",
        rsi=55.0,
        bb_width_pctile=0.15,
        vwap_discount_pct=3.0,
        vwap_pct=1.0,
        latest_candle_date=date(2026, 6, 18),
    )
    setup_eval = SetupEvaluation(
        name="foreign-bounce",
        match=SetupMatch.MATCH,
        gates=(
            SetupGate("accum_score", True, "75", ">= 70"),
            SetupGate("flow_pct", True, "5%", ">= 5%"),
            SetupGate("fvwap%", True, "3%", ">= 3%"),
        ),
        failed_reasons=(),
    )
    workflow = SwingAnalysisWorkflowUseCase(
        market_repository=FakeMarketRepository(_breakout_candles(), source="idx"),
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: {},
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate_evaluation=lambda **kwargs: SimpleNamespace(
            candidate=candidate,
            consumed_candles=(),
            consumed_broker_summaries=(),
            consumed_broker_daily_flows=(),
        ),
        evaluate_setup=lambda candidate, broker_detail: setup_eval,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_config=lambda: SimpleNamespace(),
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        rules_loader=RulesYamlLoader(),
        signal_evidence_context_builder=_fake_signal_evidence_context_builder(),
        candidate_observations_repository=FakeLearningObservationsRepository(
            ("ACCUMULATION", "COMPRESSION")
        ),
    )

    response = workflow.execute(
        _request(today=date(2026, 6, 18), setup_name="foreign-bounce")
    )

    assert response.evidence.setup_evidence.candle_source == "idx"
    assert response.evidence.setup_phase.current_phase == SetupPhaseState.BREAKOUT_CONFIRMATION
    assert response.evidence.setup_phase.sequence_valid is True


def test_swing_workflow_emits_diagnostic_strategy_rule_evidence(tmp_path):
    strategy_path = tmp_path / "strategy.yaml"
    strategy_path.write_text(
        """
version: 1
name: "Price Breakout"
default_outcome: MODERATE
rules:
  - name: close_breakout
    when:
      left:
        indicator: CLOSE
      operator: ">"
      right:
        value: 1000
    outcome: LOW_RISK
    rationale: "Close is above breakout threshold"
""",
        encoding="utf-8",
    )
    workflow = _workflow(
        FakeMarketRepository([_candle(date(2026, 6, 18))]),
        [],
    )

    response = workflow.execute(_request(strategy_name=str(strategy_path)))

    assert response.evidence is not None
    assert response.evidence.strategy_rule_evidence is not None
    assert response.evidence.strategy_rule_evidence.strategy_name == "Price Breakout"
    assert response.evidence.strategy_rule_evidence.matched_rule.rule_name == "close_breakout"
    assert response.verdict.trade_setup is None


def test_swing_workflow_only_builds_optional_evidence_when_requested():
    calls: list[str] = []
    workflow = SwingAnalysisWorkflowUseCase(
        market_repository=FakeMarketRepository([_candle(date(2026, 6, 18))]),
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: ("candles=ok",),
        build_data_freshness=lambda **kwargs: None,
        build_flow_detail=lambda **kwargs: calls.append("flow") or {"flow": True},
        build_broker_detail=lambda **kwargs: calls.append("broker") or {"broker": True},
        build_accumulation_candidate_evaluation=lambda **kwargs: None,
        evaluate_setup=lambda candidate, broker_detail: calls.append("setup") or None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: calls.append("sentiment") or (None, None),
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        rules_loader=RulesYamlLoader(),
        signal_evidence_context_builder=_fake_signal_evidence_context_builder(),
    )

    response = workflow.execute(
        _request(
            include_flow_detail=True,
            include_sentiment=True,
            setup_name="foreign-bounce",
        )
    )

    assert calls == ["flow", "broker", "setup", "sentiment"]
    assert response.flow_detail == {"flow": True}
    assert response.broker_detail == {"broker": True}
    assert response.modules["setup"] is True
    assert response.modules["sentiment"] is True
    assert response.modules["flow_detail"] is True
