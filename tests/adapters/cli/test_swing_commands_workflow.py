"""Workflow construction and delegation tests for swing commands."""

from decimal import Decimal
from types import SimpleNamespace

from src.adapters.cli import analyze_swing_commands as swing_cli
from src.adapters.cli.main import app
from tests.adapters.cli.swing_command_fixtures import runner


def test_swing_command_delegates_workflow_construction_to_builder(monkeypatch):
    captured = {}

    class FakeFreshness:
        def to_dict(self):
            return {"as_of_date": "2026-06-28", "warnings": []}

    class FakeWorkflow:
        def execute(self, request):
            captured["request"] = request
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
            )
            response.to_dict = lambda **kwargs: {
                "schema_version": 1,
                "artifact_type": "swing_analysis",
            }
            return response

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
