"""Tests for swing analysis workflow orchestration."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.services.flow_confirmation_evidence_builder import (
    FlowConfirmationEvidenceBuilder,
)
from src.application.use_case.swing_analysis_workflow_use_case import (
    SwingAnalysisDataUnavailable,
    SwingAnalysisWorkflowRequest,
    SwingAnalysisWorkflowUseCase,
    SwingEvidence,
)
from src.domain.entities.candle import Candle
from src.domain.ports.candidate_observations_repository import CandidateObservation
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupGate, SetupMatch
from src.domain.value_objects.setup_phase import SetupPhaseSnapshot, SetupPhaseState


class FakeMarketRepository:
    def __init__(self, candles: list[Candle], source: str | None = None) -> None:
        self._candles = candles
        self._source = source

    def get_candles(self, ticker: str, start_date=None, end_date=None):
        return self._candles

    def get_candle_source(self, ticker: str, on_date: date):
        return self._source


class FakeBrokerRepository:
    pass


class FakeCandidateObservationsRepository:
    def __init__(self, phases: tuple[str, ...]) -> None:
        self._phases = phases

    def save_many(self, observations):
        raise AssertionError("not used")

    def get_latest(self, ticker, snapshot_date):
        raise AssertionError("not used")

    def get_at(self, ticker, snapshot_date, captured_at):
        raise AssertionError("not used")

    def list_recent(self, ticker, *, before_date=None, limit=20):
        rows = []
        start = date(2026, 6, 1)
        for idx, phase in enumerate(self._phases):
            day = start + timedelta(days=idx)
            rows.append(
                CandidateObservation(
                    ticker=ticker.upper(),
                    snapshot_date=day,
                    captured_at=datetime(day.year, day.month, day.day, 9, 0, 0),
                    payload={
                        "schema_version": 1,
                        "workflow": "screen_accum",
                        "sub_signal_fingerprint": {
                            "setup_family": "foreign-bounce",
                            "setup_phase_current": phase,
                        },
                    },
                )
            )
        return list(reversed(rows))[:limit]


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


def _breakout_candles() -> list[Candle]:
    start = date(2026, 5, 30)
    candles = []
    for idx in range(20):
        open_ = Decimal("1000")
        high = Decimal("1010")
        close = Decimal("1005")
        volume = 1_000_000 if idx < 15 else 2_000_000
        if idx == 19:
            open_ = Decimal("1015")
            close = Decimal("1050")
            high = Decimal("1060")
        candles.append(
            Candle(
                ticker="BBCA",
                date=start + timedelta(days=idx),
                open=open_,
                high=high,
                low=Decimal("990"),
                close=close,
                volume=volume,
            )
        )
    return candles


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
        "benchmark": "IHSG",
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


def test_swing_workflow_can_emit_breakout_confirmation_with_local_volume_source():
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
            SetupGate("foreign_flow_score", True, "75", ">= 70"),
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
        build_accumulation_candidate=lambda **kwargs: candidate,
        evaluate_setup=lambda candidate, broker_detail: setup_eval,
        build_broker_quality_note=lambda **kwargs: None,
        fetch_sentiment=lambda **kwargs: (None, None),
        load_swing_config=lambda: SimpleNamespace(),
        resolve_setup_targets=lambda regime, config: (Decimal("5"), Decimal("5")),
        candidate_observations_repository=FakeCandidateObservationsRepository(
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


def test_swing_workflow_mce_regime_forwarded_to_signal_engine():
    """ADR-037: when --with-market-context is enabled, market_regime is forwarded
    to evaluate_with_context so regime conditioning can be applied canonically.

    Without MCE, market_context=None → no conditioning.
    With MCE, market_context=market_regime is passed into the signal use case.

    The FakeSignalEngine records calls to verify forwarding. TradeSetup action
    IS allowed to differ with vs without MCE (ADR-037 supersedes ADR-032).
    """
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

    fake_signal = FakeSignalEngine()
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
        signal_engine=fake_signal,
        risk_engine=FakeRiskEngine(),
    )

    fake_signal.received_market_contexts.clear()
    response_without_mce = workflow.execute(_request(with_market_context=False))
    assert response_without_mce.market_regime is None
    # Without MCE, signal engine called with market_context=None
    assert all(ctx is None for (_, ctx) in fake_signal.received_market_contexts), (
        "no market_context should be passed to signal engine when MCE disabled"
    )

    fake_signal.received_market_contexts.clear()
    response_with_mce = workflow.execute(_request(with_market_context=True))
    assert response_with_mce.market_regime is not None
    # With MCE, signal engine must receive the regime (ADR-037)
    assert any(ctx is not None for (_, ctx) in fake_signal.received_market_contexts), (
        "market_context must be forwarded to signal engine when MCE enabled (ADR-037)"
    )

    # MCE preview infra still populated
    assert response_with_mce.market_context_trade_setup_preview is not None
    assert response_with_mce.market_context_signal_preview is not None
    assert response_with_mce.verdict is not None
    assert (
        response_with_mce.verdict.market_context_trade_setup_preview
        is response_with_mce.market_context_trade_setup_preview
    )


# ─── SwingEvidence.to_dict() regression ───────────────────────────────────────

def test_swing_evidence_to_dict_includes_flow_confirmation_evidence():
    """flow_confirmation_evidence must appear in serialized workflow output."""
    candidate = SimpleNamespace(
        ticker="BBCA",
        foreign_flow_evidence=SimpleNamespace(
            component_breakdown=(
                ("cons", 40.0), ("streak", 19.0), ("vwap", 20.0),
                ("rsi", 10.0), ("flow", 10.0), ("bb", 0.0), ("inst", 15.0),
            ),
            confirmation_status="CONFIRMED",
            flow_direction="POSITIVE",
        ),
        bandar_detector=None,
        bci_label="CLUSTER",
        bci_tier1_count=3,
        latest_candle_date=date(2026, 6, 25),
    )
    flow_ev = FlowConfirmationEvidenceBuilder().build(candidate, analysis_date=date(2026, 6, 25))
    evidence = SwingEvidence(
        accumulation_candidate=None,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("0.05"),
        stop_loss_pct=Decimal("0.03"),
        regime_label=None,
        flow_confirmation_evidence=flow_ev,
    )

    d = evidence.to_dict()

    assert "flow_confirmation_evidence" in d
    fc = d["flow_confirmation_evidence"]
    assert fc is not None
    assert fc["ticker"] == "BBCA"
    assert fc["confirmation_status"] == "CONFIRMED"
    assert fc["flow_direction"] == "POSITIVE"
    assert isinstance(fc["flow_signals"], list)
    assert all(s["key"] not in ("bb", "rsi") for s in fc["flow_signals"])


def test_swing_evidence_to_dict_flow_confirmation_none_when_not_built():
    """flow_confirmation_evidence key is present but None when builder not called."""
    evidence = SwingEvidence(
        accumulation_candidate=None,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("0.05"),
        stop_loss_pct=Decimal("0.03"),
        regime_label=None,
    )

    d = evidence.to_dict()

    assert "flow_confirmation_evidence" in d
    assert d["flow_confirmation_evidence"] is None


def test_swing_evidence_to_dict_includes_setup_phase():
    phase = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        previous_phase=SetupPhaseState.COMPRESSION,
        phase_age_sessions=1,
        phase_strength=0.8,
        coverage_score=1.0,
        conviction_score=0.8,
        sequence_valid=True,
        reasons=("breakout: VWAP reclaim",),
    )
    evidence = SwingEvidence(
        accumulation_candidate=None,
        setup_eval=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        take_profit_pct=Decimal("0.05"),
        stop_loss_pct=Decimal("0.03"),
        regime_label=None,
        setup_phase=phase,
    )

    d = evidence.to_dict()

    assert d["setup_phase"]["current_phase"] == "BREAKOUT_CONFIRMATION"
    assert d["setup_phase"]["sequence_valid"] is True
