"""Workflow construction and delegation tests for swing commands."""

import json
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.adapters.cli import analyze_swing_commands as swing_cli
from src.adapters.cli.main import app
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from tests.adapters.cli.swing_command_fixtures import runner

_FAKE_SESSION = EffectiveMarketSession(
    run_at=datetime(2026, 7, 23, 16, 0),
    decision_at=datetime(2026, 7, 23, 16, 0),
    latest_completed_session=date(2026, 7, 23),
    analysis_as_of=date(2026, 7, 23),
    market_session_name="AFTER_CLOSE",
    is_eod_pending=False,
    resolution_source="test",
)


def _fake_workflow_response(*, request, effective_session=None):
    session = effective_session if effective_session is not None else _FAKE_SESSION

    class FakeFreshness:
        def to_dict(self):
            return {"as_of_date": "2026-06-28", "warnings": []}

    response = SimpleNamespace(
        ticker=request.ticker,
        today=request.today,
        refresh_actions=(),
        data_freshness=FakeFreshness(),
        flow_detail=None,
        broker_detail=None,
        candles=[],
        latest_close=Decimal("0"),
        accumulation_candidate=None,
        risk_response=None,
        atr_value=None,
        sizing=None,
        setup_eval=None,
        setup_sizing=None,
        broker_quality_note=None,
        backtest_result=None,
        sentiment_response=None,
        sentiment_warning=None,
        market_regime=None,
        take_profit_pct=Decimal("5"),
        stop_loss_pct=Decimal("5"),
        regime_label=None,
        signal_assessment=None,
        trade_setup=None,
        market_context_signal_preview=None,
        market_context_risk_preview=None,
        market_context_trade_setup_preview=None,
        verdict=SimpleNamespace(
            risk_response=None,
            market_regime=None,
            signal_assessment=None,
            trade_setup=None,
            market_context_signal_preview=None,
            market_context_risk_preview=None,
            market_context_trade_setup_preview=None,
        ),
        evidence=SimpleNamespace(
            accumulation_candidate=None,
            setup_eval=None,
            backtest_result=None,
            sentiment_response=None,
            sentiment_warning=None,
            sector_context_evidence=None,
            institutional_accumulation_evidence=None,
            strategy_rule_evidence=None,
        ),
        diagnostics=SimpleNamespace(
            data_freshness=FakeFreshness(),
            flow_detail=None,
            broker_detail=None,
            broker_quality_note=None,
        ),
        modules={},
        warnings=(),
        effective_session=session,
    )
    response.to_dict = lambda **kwargs: {
        "schema_version": 1,
        "artifact_type": "swing_analysis",
        "effective_session": session.to_dict(),
    }
    return response


def test_swing_command_delegates_workflow_construction_to_builder(monkeypatch):
    captured = {}

    class FakeWorkflow:
        def execute(self, request):
            captured["request"] = request
            return _fake_workflow_response(request=request)

    def fake_builder(**kwargs):
        captured["builder"] = kwargs
        return FakeWorkflow()

    monkeypatch.setattr(swing_cli, "create_swing_analysis_workflow", fake_builder)

    result = runner.invoke(
        app,
        ["analyze", "swing", "BBCA", "--setup", "foreign-bounce", "--format", "json"],
    )

    assert result.exit_code == 0
    assert captured["builder"]["setup_name"] == "foreign-bounce"
    assert captured["request"].ticker == "BBCA"


def test_swing_command_threads_as_of_to_request_today(monkeypatch):
    captured = {}

    class FakeWorkflow:
        def execute(self, request):
            captured["request"] = request
            return _fake_workflow_response(request=request)

    monkeypatch.setattr(
        swing_cli,
        "create_swing_analysis_workflow",
        lambda **kwargs: FakeWorkflow(),
    )

    result = runner.invoke(
        app,
        ["analyze", "swing", "BBCA", "--as-of", "2026-07-23", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    assert captured["request"].today == date(2026, 7, 23)


def test_swing_command_rejects_invalid_as_of(monkeypatch):
    def fake_builder(**kwargs):
        raise AssertionError("workflow must not run when --as-of is invalid")

    monkeypatch.setattr(swing_cli, "create_swing_analysis_workflow", fake_builder)

    result = runner.invoke(
        app,
        ["analyze", "swing", "BBCA", "--as-of", "not-a-date"],
    )

    assert result.exit_code == 1
    assert "Invalid --as-of" in result.stderr


def test_swing_json_includes_effective_session(monkeypatch):
    class FakeWorkflow:
        def execute(self, request):
            return _fake_workflow_response(request=request)

    monkeypatch.setattr(
        swing_cli,
        "create_swing_analysis_workflow",
        lambda **kwargs: FakeWorkflow(),
    )

    result = runner.invoke(
        app,
        ["analyze", "swing", "BBCA", "--as-of", "2026-07-23", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["effective_session"]["analysis_as_of"] == "2026-07-23"
    assert payload["effective_session"]["is_eod_pending"] is False


def test_analyze_swing_help_exposes_as_of():
    result = runner.invoke(app, ["analyze", "swing", "--help"])

    assert result.exit_code == 0
    assert "--as-of" in result.stdout


def test_swing_display_path_prefers_grouped_response_contracts(monkeypatch):
    captured = {}
    flat_data = object()
    grouped_data = object()
    flat_accum = object()
    grouped_accum = object()

    class FakeWorkflow:
        def execute(self, request):
            return SimpleNamespace(
                ticker=request.ticker,
                today=request.today,
                refresh_actions=(),
                data_freshness=flat_data,
                flow_detail=None,
                broker_detail=None,
                candles=[],
                latest_close=Decimal("0"),
                accumulation_candidate=flat_accum,
                risk_response="flat-risk",
                atr_value=None,
                sizing=None,
                setup_eval=None,
                setup_sizing=None,
                broker_quality_note=None,
                backtest_result=None,
                sentiment_response=None,
                sentiment_warning=None,
                market_regime="flat-market",
                take_profit_pct=Decimal("5"),
                stop_loss_pct=Decimal("5"),
                regime_label=None,
                signal_assessment="flat-signal",
                trade_setup="flat-setup",
                market_context_signal_preview=None,
                market_context_risk_preview=None,
                market_context_trade_setup_preview=None,
                verdict=SimpleNamespace(
                    risk_response="grouped-risk",
                    market_regime="grouped-market",
                    signal_assessment="grouped-signal",
                    trade_setup="grouped-setup",
                    market_context_signal_preview=None,
                    market_context_risk_preview=None,
                    market_context_trade_setup_preview=None,
                ),
                evidence=SimpleNamespace(
                    accumulation_candidate=grouped_accum,
                    setup_eval=None,
                    backtest_result=None,
                    sentiment_response=None,
                    sentiment_warning=None,
                    take_profit_pct=Decimal("6"),
                    stop_loss_pct=Decimal("4"),
                    regime_label=None,
                    sector_context_evidence=None,
                    institutional_accumulation_evidence=None,
                    strategy_rule_evidence=None,
                ),
                diagnostics=SimpleNamespace(
                    data_freshness=grouped_data,
                    flow_detail="grouped-flow",
                    broker_detail="grouped-broker",
                    broker_quality_note="grouped-note",
                ),
                modules={},
                warnings=(),
                effective_session=None,
            )

    monkeypatch.setattr(
        swing_cli,
        "create_swing_analysis_workflow",
        lambda **kwargs: FakeWorkflow(),
    )
    monkeypatch.setattr(
        swing_cli,
        "print_swing_output",
        lambda ctx: captured.update({"ctx": ctx}),
    )

    result = runner.invoke(app, ["analyze", "swing", "BBCA"])

    assert result.exit_code == 0
    ctx = captured["ctx"]
    assert ctx.diagnostics.data_freshness is grouped_data
    assert ctx.evidence.accumulation_candidate is grouped_accum
    assert ctx.verdict.risk_response == "grouped-risk"
    assert ctx.verdict.market_regime == "grouped-market"
    assert ctx.verdict.signal_assessment == "grouped-signal"
    assert ctx.verdict.trade_setup == "grouped-setup"
