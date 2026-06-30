"""Tests for swing analysis workflow orchestration."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisDataUnavailable,
    SwingAnalysisWorkflowRequest,
    SwingAnalysisWorkflowUseCase,
)
from src.domain.entities.candle import Candle


class FakeMarketRepository:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def get_candles(self, ticker: str, start_date=None, end_date=None):
        return self._candles


class FakeBrokerRepository:
    pass


class FakeRegistry:
    def compute(self, name: str, candles: list[Candle], period: int):
        if name == "ATR":
            return [(candles[-1].date, Decimal("25"))]
        return []


def _candle(day: date) -> Candle:
    return Candle(
        ticker="BBCA",
        date=day,
        open=Decimal("1000"),
        high=Decimal("1025"),
        low=Decimal("990"),
        close=Decimal("1010"),
        volume=1_000_000,
    )


def _request(**overrides) -> SwingAnalysisWorkflowRequest:
    values = {
        "ticker": "BBCA",
        "today": date(2026, 6, 18),
        "strategy_name": None,
        "setup_name": None,
        "window": 7,
        "flow_window": 30,
        "capital": None,
        "risk_pct": 1.0,
        "entry_price": None,
        "atr_mult": 1.5,
        "rr": 2.0,
        "include_sentiment": False,
        "include_flow_detail": False,
        "include_signal_detail": False,
        "include_risk_detail": False,
        "include_market_detail": False,
        "sentiment_verbose": False,
        "auto_refresh": False,
        "force_refresh": False,
        "with_market_context": False,
        "regime_universe": "idx80",
        "benchmark": "^JKSE",
        "db_path": Path("data.db"),
        "with_technical_gate": False,
    }
    values.update(overrides)
    return SwingAnalysisWorkflowRequest(**values)


def _workflow(market_repo, calls: list[str]) -> SwingAnalysisWorkflowUseCase:
    return SwingAnalysisWorkflowUseCase(
        market_repository=market_repo,
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: calls.append("refresh") or ("candles=ok",),
        build_data_freshness=lambda **kwargs: {"freshness": kwargs["refresh_actions"]},
        build_flow_detail=lambda **kwargs: {"flow_window": kwargs["window_sessions"]},
        build_broker_detail=lambda **kwargs: {"broker_window": kwargs["window_sessions"]},
        build_accumulation_candidate=lambda **kwargs: {"ticker": kwargs["ticker"]},
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
    )


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
    assert response.evidence.accumulation_candidate == {"ticker": "BBCA"}


def test_swing_workflow_runs_auto_refresh_when_enabled():
    calls: list[str] = []
    workflow = _workflow(
        FakeMarketRepository([_candle(date(2026, 6, 18))]),
        calls,
    )

    response = workflow.execute(_request(auto_refresh=True))

    assert calls == ["refresh"]
    assert response.refresh_actions == ("candles=ok",)


def test_swing_workflow_raises_when_candles_are_missing():
    workflow = _workflow(FakeMarketRepository([]), [])

    with pytest.raises(SwingAnalysisDataUnavailable):
        workflow.execute(_request())


def test_swing_workflow_records_accumulation_failure_warning():
    def build_accumulation_candidate(**kwargs):
        raise RuntimeError("no broker rows")

    workflow = SwingAnalysisWorkflowUseCase(
        market_repository=FakeMarketRepository([_candle(date(2026, 6, 18))]),
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: ("candles=ok",),
        build_data_freshness=lambda **kwargs: None,
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate=build_accumulation_candidate,
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
    )

    response = workflow.execute(_request())

    assert response.evidence is not None
    assert response.evidence.accumulation_candidate is None
    assert "Accumulation unavailable: no broker rows" in response.warnings


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
        build_accumulation_candidate=lambda **kwargs: None,
        evaluate_setup=lambda candidate, broker_detail: calls.append("setup") or None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: calls.append("sentiment") or (None, None),
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
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


def test_swing_workflow_canonical_trade_setup_unaffected_by_market_context():
    """TradeSetup must be identical whether or not MCE is requested."""
    from dataclasses import replace as dc_replace
    from src.domain.value_objects.market_context import MarketContext, MarketRegime
    from src.domain.value_objects.signal_assessment import SignalAssessment, SignalStrength, EntryQuality
    from src.application.use_case.assess_signal_use_case import AssessSignalResponse

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
    )

    def _raw_signal_response():
        return AssessSignalResponse(
            ticker="BBCA",
            assessment=_RAW_SIGNAL,
            coverage_warning=None,
        )

    class FakeSignalEngine:
        def evaluate(self, ticker, as_of_date=None, market_context=None):
            return _raw_signal_response()

        def evaluate_with_context(self, ticker, signal_context, market_context=None):
            return _raw_signal_response()

        def apply_market_context(self, response, market_context):
            from src.application.services.signal_engine import _apply_market_context
            return _apply_market_context(response, market_context)

    class FakeRiskEngine:
        def _make_response(self):
            from src.application.use_case.assess_risk_use_case import AssessRiskResponse
            from src.domain.value_objects.risk_assessment import RiskAssessment
            from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
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

    workflow = SwingAnalysisWorkflowUseCase(
        market_repository=FakeMarketRepository([_candle(date(2026, 6, 18))]),
        broker_repository=FakeBrokerRepository(),
        registry=FakeRegistry(),
        refresh_data=lambda **kwargs: ("disabled",),
        build_data_freshness=lambda **kwargs: {"freshness": "ok"},
        build_flow_detail=lambda **kwargs: None,
        build_broker_detail=lambda **kwargs: None,
        build_accumulation_candidate=lambda **kwargs: None,
        evaluate_setup=lambda candidate, broker_detail: None,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_config=lambda: {},
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        evaluate_market_context=lambda **kwargs: _RISK_OFF_CONTEXT,
        signal_engine=FakeSignalEngine(),
        risk_engine=FakeRiskEngine(),
    )

    response_with_mce = workflow.execute(_request(with_market_context=True))
    response_without_mce = workflow.execute(_request(with_market_context=False))

    assert response_without_mce.market_regime is None
    assert response_with_mce.market_regime is not None

    assert response_without_mce.trade_setup is not None
    assert response_with_mce.trade_setup is not None
    assert response_with_mce.trade_setup.action == response_without_mce.trade_setup.action, (
        "canonical TradeSetup must be identical regardless of --with-market-context"
    )

    assert response_with_mce.market_context_trade_setup_preview is not None
    assert response_with_mce.market_context_signal_preview is not None
    assert response_with_mce.verdict is not None
    assert (
        response_with_mce.verdict.market_context_trade_setup_preview
        is response_with_mce.market_context_trade_setup_preview
    )
