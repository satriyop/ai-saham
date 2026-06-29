"""Tests for swing command helper logic."""

import json
import logging
import inspect
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from src.adapters.cli import analyze_swing_commands as swing_cli
from src.adapters.cli.analyze_swing_broker_display import (
    build_broker_detail as _build_broker_detail_base,
)
from src.adapters.cli.analyze_swing_broker_display import (
    build_broker_quality_note as _build_broker_quality_note,
)
from src.adapters.cli.analyze_swing_broker_display import (
    build_flow_detail as _build_flow_detail,
)
from src.adapters.cli.analyze_swing_commands import (
    FOREIGN_BOUNCE_SETUP_NAME,
    _evaluate_swing_setup,
    _fetch_swing_sentiment,
    _print_swing_output,
)
from src.adapters.cli.analyze_swing_display import (
    format_failed_gates_summary as _format_failed_gates_summary,
)
from src.adapters.cli.main import app
from src.application.services.swing_data_freshness import SwingDataFreshness
from src.application.use_case.accumulation_screen_use_case import AccumulationCandidate
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType
from src.domain.value_objects.accumulation_evidence import AccumulationEvidence
from src.domain.value_objects.setup_evaluation import SetupEvaluation, SetupGate, SetupMatch

runner = CliRunner()


def test_swing_command_defaults_do_not_apply_setup_and_include_regime():
    params = inspect.signature(swing_cli.swing).parameters

    assert params["setup"].default is None
    assert params["with_market_context"].default is False
    assert params["strategy"].default is None
    assert "profile" not in params


def test_swing_profile_flag_is_removed():
    result = runner.invoke(app, ["analyze", "swing", "BBCA", "--profile", "balanced"])
    assert result.exit_code != 0


def test_old_regime_flags_fail_as_unknown_options():
    result_with = runner.invoke(app, ["analyze", "swing", "BBCA", "--with-regime"])
    assert result_with.exit_code != 0

    result_no = runner.invoke(app, ["analyze", "swing", "BBCA", "--no-regime"])
    assert result_no.exit_code != 0


def test_swing_deprecated_no_backtest_flag_is_removed():
    result = runner.invoke(app, ["analyze", "swing", "BBCA", "--no-backtest"])

    assert result.exit_code != 0


def test_swing_deprecated_no_sentiment_flag_is_removed():
    result = runner.invoke(app, ["analyze", "swing", "BBCA", "--no-sentiment"])

    assert result.exit_code != 0


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
    payload = json.loads(result.output)
    assert payload["artifact_type"] == "swing_analysis"
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
        "_print_swing_output",
        lambda **kwargs: captured.update(kwargs),
    )

    result = runner.invoke(app, ["analyze", "swing", "BBCA"])

    assert result.exit_code == 0
    assert captured["data_freshness"] is grouped_data
    assert captured["accum"] is grouped_accum
    assert captured["risk_resp"] == "grouped-risk"
    assert captured["market_regime"] == "grouped-market"
    assert captured["signal_assessment"] == "grouped-signal"
    assert captured["trade_setup"] == "grouped-setup"


def _build_broker_detail(*args, **kwargs):
    return _build_broker_detail_base(
        *args,
        **kwargs,
        smart_money_brokers=swing_cli.SMART_MONEY_BROKERS,
        noise_brokers=swing_cli.NOISE_BROKERS,
        broker_weights=swing_cli.BROKER_WEIGHTS,
        smart_share_threshold_pct=swing_cli._SC.smart_share_threshold_pct,
    )


class FakeBrokerSummaryRepository:
    def __init__(self, summaries):
        self._summaries = summaries

    def get_broker_summaries(self, ticker: str, start_date=None, end_date=None):
        return [
            summary
            for summary in self._summaries
            if summary.ticker == ticker
            and (start_date is None or summary.date >= start_date)
            and (end_date is None or summary.date <= end_date)
        ]


def _tx(
    code: str,
    name: str,
    buy: str,
    sell: str,
    broker_type: BrokerType = BrokerType.FOREIGN,
) -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=name,
        broker_type=broker_type,
        buy_lot=1000,
        sell_lot=500,
        buy_value=Decimal(buy),
        sell_value=Decimal(sell),
        avg_buy_price=Decimal("1000"),
        avg_sell_price=Decimal("1000"),
    )


def _summary(
    day: date,
    buy: str,
    sell: str,
    total: str = "1000000000",
    top_buyers: tuple[BrokerTransaction, ...] = (),
    top_sellers: tuple[BrokerTransaction, ...] = (),
    source: str = "stockbit",
) -> BrokerSummary:
    net_value = Decimal(buy) - Decimal(sell)
    return BrokerSummary(
        ticker="BBCA",
        date=day,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=Decimal(buy),
        foreign_sell_value=Decimal(sell),
        foreign_buy_lot=max(int(net_value), 0),
        foreign_sell_lot=max(-int(net_value), 0),
        total_value=Decimal(total),
        total_lot=1000,
        source=source,
    )


def _candidate(**overrides) -> AccumulationCandidate:
    if "score" in overrides:
        overrides["accum_score"] = overrides.pop("score")
    values = {
        "ticker": "BBCA",
        "window_days": 7,
        "net_buy_days": 5,
        "total_days": 7,
        "net_buy_ratio": 5 / 7,
        "total_net_value": Decimal("10000000000"),
        "consecutive_streak": 3,
        "foreign_vwap": Decimal("1030"),
        "current_price": Decimal("1000"),
        "vwap_discount_pct": 3.0,
        "rsi": 55.0,
        "trend": "SIDE",
        "accum_score": 70.0,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


def test_foreign_bounce_passes_all_gates():
    evaluation = _evaluate_swing_setup(FOREIGN_BOUNCE_SETUP_NAME, _candidate())

    assert evaluation.name == FOREIGN_BOUNCE_SETUP_NAME
    assert evaluation.passed is True
    assert evaluation.match == SetupMatch.MATCH
    assert evaluation.failed_reasons == ()


def test_foreign_bounce_reports_failed_gates():
    evaluation = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=70.0, trend="DOWN"),
    )

    assert evaluation.passed is False
    assert evaluation.match == SetupMatch.PARTIAL
    assert any("trend" in reason for reason in evaluation.failed_reasons)


def test_failed_gates_summary_includes_all_failed_reasons():
    evaluation = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(
            score=26.8,
            vwap_discount_pct=-0.7,
            trend="DOWN",
            avg_flow_ratio=-3.0,
            rsi=32.0,
        )
    )

    summary = _format_failed_gates_summary(evaluation)

    assert "score: 26.8" in summary
    assert "fvwap%: -0.7%" in summary
    assert "trend: DOWN" in summary
    assert "flow_pct: -3.0%" in summary


def test_foreign_bounce_missing_accumulation_is_avoid():
    evaluation = _evaluate_swing_setup(FOREIGN_BOUNCE_SETUP_NAME, None)

    assert evaluation.passed is False
    assert evaluation.match == SetupMatch.NO_MATCH


def test_flow_detail_uses_latest_broker_sessions():
    detail = _build_flow_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(date(2026, 6, 1), "120000000", "20000000"),
                _summary(date(2026, 6, 2), "10000000", "50000000"),
                _summary(date(2026, 6, 3), "80000000", "10000000"),
                _summary(date(2026, 6, 4), "90000000", "10000000"),
            ]
        ),
        window_sessions=3,
        as_of_date=date(2026, 6, 4),
    )

    assert detail is not None
    assert detail.available_sessions == 3
    assert detail.from_date == date(2026, 6, 2)
    assert detail.through_date == date(2026, 6, 4)
    assert detail.total_net_flow == Decimal("110000000")
    assert detail.buy_sessions == 2
    assert detail.sell_sessions == 1
    assert detail.consecutive_buy_sessions == 2
    assert detail.latest_net_flow == Decimal("80000000")
    assert detail.to_dict()["window_sessions"] == 3


def test_broker_detail_aggregates_named_brokers_across_investor_types():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "120000000",
                    "20000000",
                    top_buyers=(
                        _tx("AK", "UBS", "70000000", "10000000"),
                        _tx("CC", "Mandiri", "40000000", "5000000"),
                    ),
                    top_sellers=(_tx("KZ", "CLSA", "5000000", "30000000"),),
                ),
                _summary(
                    date(2026, 6, 2),
                    "100000000",
                    "20000000",
                    top_buyers=(
                        _tx("AK", "UBS", "50000000", "10000000"),
                        _tx("YP", "Mirae", "35000000", "5000000", BrokerType.LOCAL),
                    ),
                    top_sellers=(_tx("DB", "Deutsche", "5000000", "25000000"),),
                ),
                _summary(
                    date(2026, 6, 3),
                    "90000000",
                    "20000000",
                    top_buyers=(
                        _tx("CC", "Mandiri", "45000000", "5000000"),
                        _tx("YP", "Mirae", "30000000", "5000000", BrokerType.LOCAL),
                    ),
                    top_sellers=(),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 3),
    )

    assert detail is not None
    assert detail.detail_sessions == 3
    assert detail.through_date == date(2026, 6, 3)
    assert detail.top_buyers[0].broker_code == "AK"
    assert detail.top_buyers[0].net_value == Decimal("100000000")
    assert detail.top_buyers[0].active_sessions == 2
    assert detail.top_sellers[0].broker_code == "KZ"
    assert detail.top_sellers[0].net_value == Decimal("-25000000")
    assert detail.smart_flow == Decimal("55000000")
    assert detail.noise_flow == Decimal("55000000")
    assert detail.neutral_flow == Decimal("75000000")
    assert detail.weighted_net_flow == Decimal("185000000.0")
    assert detail.smart_share_pct == 29.7
    assert detail.broker_weight_quality == "smart support"
    assert detail.quality == "broad accumulation"
    assert detail.to_dict()["top_buyers"][0]["broker_code"] == "AK"
    buyer_rows = {row["broker_code"]: row for row in detail.to_dict()["top_buyers"]}
    assert buyer_rows["YP"]["broker_type"] == "LOCAL"
    assert detail.to_dict()["smart_flow"] == "55000000"
    assert detail.to_dict()["broker_weight_quality"] == "smart support"


def test_broker_detail_marks_latest_selling_as_recent_distribution():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "120000000",
                    "20000000",
                    top_buyers=(_tx("AK", "UBS", "90000000", "10000000"),),
                ),
                _summary(
                    date(2026, 6, 2),
                    "10000000",
                    "80000000",
                    top_buyers=(_tx("CC", "Mandiri", "20000000", "5000000"),),
                    top_sellers=(_tx("AK", "UBS", "5000000", "70000000"),),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 2),
    )

    assert detail is not None
    assert detail.quality == "recent distribution"
    assert detail.smart_flow == Decimal("15000000")
    assert detail.noise_flow == Decimal("0")
    assert detail.broker_weight_quality == "smart distribution watch"


def test_broker_detail_marks_noise_led_buying():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "180000000",
                    "20000000",
                    top_buyers=(
                        _tx("YP", "CGS-CIMB", "100000000", "10000000", BrokerType.LOCAL),
                        _tx("XL", "Stockbit", "40000000", "10000000", BrokerType.LOCAL),
                        _tx("XC", "Ajaib", "35000000", "5000000", BrokerType.LOCAL),
                    ),
                    top_sellers=(_tx("AK", "UBS", "5000000", "20000000"),),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )

    assert detail is not None
    assert detail.noise_flow == Decimal("150000000")
    assert detail.smart_flow == Decimal("-15000000")
    assert detail.weighted_net_flow == Decimal("52500000.0")
    assert detail.broker_weight_quality == "noisy accumulation"


def test_broker_quality_note_warns_when_enter_is_noise_led():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "180000000",
                    "20000000",
                    top_buyers=(
                        _tx("YP", "CGS-CIMB", "100000000", "10000000", BrokerType.LOCAL),
                        _tx("XL", "Stockbit", "40000000", "10000000", BrokerType.LOCAL),
                    ),
                    top_sellers=(),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )
    setup = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=75, trend="SIDE"),
    )

    note = _build_broker_quality_note(detail, setup)

    assert note is not None
    assert note.level == "warning"
    assert "noise-led" in note.message


def test_broker_quality_note_supports_watch_when_smart_buying():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "120000000",
                    "20000000",
                    top_buyers=(_tx("AK", "UBS", "90000000", "10000000"),),
                    top_sellers=(),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )
    setup = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=68, trend="SIDE"),
    )

    note = _build_broker_quality_note(detail, setup)

    assert note is not None
    assert note.level == "support"
    assert "watchlist priority" in note.message


def test_broker_quality_note_warns_on_smart_selling():
    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "20000000",
                    "120000000",
                    top_buyers=(_tx("CC", "Mandiri", "20000000", "5000000"),),
                    top_sellers=(_tx("AK", "UBS", "5000000", "90000000"),),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )
    setup = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=75, trend="SIDE"),
    )

    note = _build_broker_quality_note(detail, setup)

    assert note is not None
    assert note.level == "warning"
    assert "smart-money net selling" in note.message
    assert "%" in note.message


def test_broker_quality_note_skips_warn_on_minor_smart_selling():
    """Smart selling below 15% share threshold must not fire the smart-selling warning.

    AK sells 5M, HD (neutral) buys 100M → smart sell share ~5% → below threshold.
    """
    from src.adapters.cli.analyze_swing_broker_display import build_broker_quality_note

    detail = _build_broker_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository(
            [
                _summary(
                    date(2026, 6, 1),
                    "100000000",
                    "5000000",
                    top_buyers=(_tx("HD", "Mandiri", "100000000", "0"),),
                    top_sellers=(_tx("AK", "UBS", "0", "5000000"),),
                ),
            ]
        ),
        window_sessions=5,
        as_of_date=date(2026, 6, 1),
    )
    setup = _evaluate_swing_setup(
        FOREIGN_BOUNCE_SETUP_NAME,
        _candidate(score=75, trend="SIDE"),
    )

    note = build_broker_quality_note(detail, setup, smart_sell_min_share_pct=15.0)

    assert note is None or "smart-money net selling" not in (note.message or "")


class NoisyNewsProvider:
    provider_name = "noisy"

    def fetch_headlines(self, ticker: str, max_headlines: int = 20, days: int = 3):
        print("RAW_SENTIMENT_STDOUT")
        print("RAW_SENTIMENT_STDERR", file=sys.stderr)
        logging.getLogger("ai_saham.sentiment").warning("RAW_SENTIMENT_LOG")
        raise RuntimeError("RAW_SENTIMENT_EXCEPTION")


def test_fetch_swing_sentiment_suppresses_provider_noise_by_default(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_workflow_factory.SentimentFactory.create_news_provider",
        lambda: NoisyNewsProvider(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_workflow_factory.SentimentFactory.create_classifier",
        lambda use_ai=False: object(),
    )

    response, warning = _fetch_swing_sentiment("BBCA", sentiment_verbose=False)

    captured = capsys.readouterr()
    assert response is None
    assert warning == "News unavailable (provider fetch failed)."
    assert "RAW_SENTIMENT" not in captured.out
    assert "RAW_SENTIMENT" not in captured.err


def test_fetch_swing_sentiment_verbose_keeps_provider_details(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_workflow_factory.SentimentFactory.create_news_provider",
        lambda: NoisyNewsProvider(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_workflow_factory.SentimentFactory.create_classifier",
        lambda use_ai=False: object(),
    )

    response, warning = _fetch_swing_sentiment("BBCA", sentiment_verbose=True)

    captured = capsys.readouterr()
    assert response is None
    assert warning == "Sentiment fetch failed: RAW_SENTIMENT_EXCEPTION"
    assert "RAW_SENTIMENT_STDOUT" in captured.out
    assert "RAW_SENTIMENT_STDERR" in captured.err


def test_swing_backtest_unknown_setup_error():
    result = runner.invoke(app, ["trade", "backtest-swing", "--setup", "unknown"])

    assert result.exit_code != 0
    assert "unknown swing setup" in result.output.lower()
    assert FOREIGN_BOUNCE_SETUP_NAME in result.output


def test_regime_command_accepts_explicit_ticker_with_empty_cache(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "analyze",
            "regime",
            "BBCA",
            "--universe",
            "cached",
            "--db",
            str(tmp_path / "empty.db"),
            "--as-of",
            "2026-06-12",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Market Context" in result.output


def test_swing_backtest_rejects_invalid_allowed_regime():
    result = runner.invoke(
        app,
        [
            "trade",
            "backtest-swing",
            "BBCA",
            "--allow-regimes",
            "CALM",
        ],
    )

    assert result.exit_code != 0
    assert "--allow-regimes" in result.output


def test_swing_compare_rejects_unknown_variant():
    result = runner.invoke(
        app,
        [
            "analyze",
            "swing-compare",
            "BBCA",
            "--variants",
            "baseline,unknown",
        ],
    )

    assert result.exit_code != 0
    assert "unknown" in result.output.lower()
    assert "baseline" in result.output


def test_swing_output_renders_rich_decision_overview(capsys):
    setup = SetupEvaluation(
        name=FOREIGN_BOUNCE_SETUP_NAME,
        match=SetupMatch.PARTIAL,
        gates=(
            SetupGate("score", True, "70.0", ">= 55"),
            SetupGate("trend", False, "DOWN", "SIDE"),
        ),
        failed_reasons=("trend: DOWN (required SIDE)",),
    )

    _print_swing_output(
        ticker="BBCA",
        today=date(2026, 6, 19),
        strategy_name="foreign-accumulation",
        data_freshness=SwingDataFreshness(
            as_of_date=date(2026, 6, 19),
            candle_start=date(2026, 1, 1),
            candle_end=date(2026, 6, 18),
            broker_start=date(2026, 1, 1),
            broker_end=date(2026, 6, 18),
            warnings=("Latest candle is stale",),
        ),
        flow_detail=None,
        broker_detail=None,
        window=7,
        accum=_candidate(score=70.0, trend="DOWN"),
        risk_resp=None,
        atr_value=None,
        sizing=None,
        setup_eval=setup,
        setup_sizing=None,
        broker_quality_note=None,
        market_regime=None,
        capital=None,
        backtest_result=None,
        sentiment_resp=None,
        sentiment_warning=None,
        sentiment_verbose=False,
        include_strategy=False,
        include_sentiment=False,
        include_flow_detail=False,
        include_signal_detail=False,
        include_risk_detail=False,
        include_market_detail=False,
    )

    out = capsys.readouterr().out
    assert "Swing Analysis - BBCA" in out
    assert "Verdict" in out
    assert "Signal" in out
    assert "Risk" in out
    assert "SETUP EVIDENCE" in out
    assert "Plan" in out
    assert "Setup is partial" in out
    assert "Data" in out


def test_swing_output_renders_optional_evidence_as_separate_panels(capsys):
    strength = SimpleNamespace(value="STRONG")
    entry_quality = SimpleNamespace(value="ENTER")
    signal_assessment = SimpleNamespace(
        assessment=SimpleNamespace(
            score=82,
            strength=strength,
            entry_quality=entry_quality,
            score_label="82/100",
            rationale=("foreign flow supportive", "bandar supportive"),
            breakdown_dict={
                "bandar_intensity": 80.0,
                "foreign_flow_quality": 75.0,
                "insider_activity": 50.0,
                "seasonality_edge": 60.0,
                "analyst_consensus": 70.0,
                "forward_valuation": 55.0,
            },
        ),
        coverage_warning=None,
    )
    risk_resp = SimpleNamespace(
        assessment=SimpleNamespace(
            risk_level_name="LOW_RISK",
            confidence=100,
            gate_triggered=None,
            indicators=SimpleNamespace(
                sma=Decimal("1000"),
                ema=Decimal("1010"),
                rsi=Decimal("55"),
            ),
            rationale_list=("trend constructive",),
        )
    )
    backtest_result = SimpleNamespace(
        trade_count=12,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 18),
        win_rate=Decimal("58.3"),
        profit_factor=Decimal("1.42"),
        max_drawdown_pct=Decimal("6.5"),
        avg_win=Decimal("500000"),
        avg_loss=Decimal("-300000"),
    )
    sentiment_resp = SimpleNamespace(
        warning=None,
        snapshot=SimpleNamespace(
            overall_sentiment=SimpleNamespace(value="POSITIVE"),
            total_count=8,
            positive_count=4,
            neutral_count=3,
            negative_count=1,
            confidence_pct=75,
        ),
    )

    _print_swing_output(
        ticker="BBCA",
        today=date(2026, 6, 19),
        strategy_name="foreign-accumulation",
        data_freshness=SwingDataFreshness(
            as_of_date=date(2026, 6, 19),
            candle_start=date(2026, 1, 1),
            candle_end=date(2026, 6, 18),
            broker_start=date(2026, 1, 1),
            broker_end=date(2026, 6, 18),
            warnings=(),
        ),
        flow_detail=None,
        broker_detail=None,
        window=7,
        accum=_candidate(score=82.0, trend="SIDE"),
        risk_resp=risk_resp,
        atr_value=None,
        sizing=None,
        setup_eval=None,
        setup_sizing=None,
        broker_quality_note=None,
        market_regime=None,
        capital=None,
        backtest_result=backtest_result,
        sentiment_resp=sentiment_resp,
        sentiment_warning=None,
        sentiment_verbose=False,
        include_strategy=True,
        include_sentiment=True,
        include_flow_detail=True,
        include_signal_detail=True,
        include_risk_detail=True,
        include_market_detail=False,
        signal_assessment=signal_assessment,
        market_context_trade_setup_preview=None,
    )

    out = capsys.readouterr().out
    assert "SIGNAL DETAIL" in out
    assert "Explains the Signal column in Verdict" in out
    assert "Scale: SignalEngine 0-100. Used in final TradeSetup: yes." in out
    assert "Composite accumulation evidence 82.0/120" in out
    assert "RISK DETAIL" in out
    assert "FLOW / BROKER DETAIL" in out
    assert "Composite Accumulation Evidence (7 broker sessions)" in out
    assert "ENTER-ZONE / FLOW POSITIVE" in out
    assert "Longer-term flow context below is diagnostic only" in out
    assert "Accum Score" in out
    assert "STRATEGY EVIDENCE" in out
    assert "2026-01-01 to 2026-06-18" in out
    assert "SENTIMENT EVIDENCE" in out
    assert "DETAILED HISTORY & SENTIMENT" not in out


def test_swing_flow_detail_calls_out_conflicted_negative_flow(capsys):
    risk_resp = SimpleNamespace(
        assessment=SimpleNamespace(
            risk_level_name="BLOCKED",
            confidence=80,
            gate_triggered="BandarGate",
            gate_confidence=80,
            indicators=SimpleNamespace(
                sma=Decimal("4756"),
                ema=Decimal("4869"),
                rsi=Decimal("42"),
            ),
            rationale_list=("Bandar distribution (Big Dist)",),
        )
    )
    signal_assessment = SimpleNamespace(
        assessment=SimpleNamespace(
            score=59,
            strength=SimpleNamespace(value="MODERATE"),
            entry_quality=SimpleNamespace(value="WATCH"),
            score_label="59/100",
            rationale=("Foreign flow: 36/100", "Bandar accumulation: 8/100"),
            breakdown_dict={
                "bandar_intensity": 8.3,
                "foreign_flow_quality": 35.7,
            },
        ),
        coverage_warning=None,
    )
    flow_detail = SimpleNamespace(
        window_sessions=30,
        through_date=date(2026, 6, 26),
        from_date=date(2026, 5, 7),
        total_net_flow=Decimal("-1130000000000"),
        available_sessions=30,
        buy_sessions=8,
        sell_sessions=22,
        consecutive_buy_sessions=0,
        avg_flow_ratio_pct=-11.08,
        latest_net_flow=Decimal("-87140000000"),
        latest_flow_ratio_pct=-28.14,
    )
    accum = _candidate(
        score=42.8,
        consecutive_streak=0,
        net_buy_days=3,
        total_days=7,
        avg_flow_ratio=-9.0,
        accumulation_evidence=AccumulationEvidence(
            ticker="ASII",
            snapshot_date=date(2026, 6, 27),
            accum_score=42.8,
            max_score=120.0,
            breakdown=(
                ("cons", 17.1),
                ("streak", 0.0),
                ("vwap", 1.2),
                ("rsi", 9.4),
                ("flow", 0.0),
                ("bb", 0.0),
                ("inst", 15.0),
            ),
        ),
        bandar_detector=SimpleNamespace(
            label="Dist | today=Big Dist",
            accumulation_score=-6,
            is_accumulating=False,
            is_distributing=True,
        ),
    )

    _print_swing_output(
        ticker="ASII",
        today=date(2026, 6, 27),
        strategy_name=None,
        data_freshness=SwingDataFreshness(
            as_of_date=date(2026, 6, 27),
            candle_start=date(2026, 1, 1),
            candle_end=date(2026, 6, 26),
            broker_start=date(2026, 1, 1),
            broker_end=date(2026, 6, 26),
            warnings=(),
        ),
        flow_detail=flow_detail,
        broker_detail=None,
        window=7,
        accum=accum,
        risk_resp=risk_resp,
        atr_value=None,
        sizing=None,
        setup_eval=None,
        setup_sizing=None,
        broker_quality_note=None,
        market_regime=None,
        capital=None,
        backtest_result=None,
        sentiment_resp=None,
        sentiment_warning=None,
        sentiment_verbose=False,
        include_strategy=False,
        include_sentiment=False,
        include_flow_detail=True,
        include_signal_detail=True,
        include_risk_detail=False,
        include_market_detail=False,
        signal_assessment=signal_assessment,
        market_context_trade_setup_preview=None,
    )

    out = capsys.readouterr().out
    assert "WATCH-ZONE / FLOW NEGATIVE" in out
    assert "current foreign flow is not confirming" in out
    assert "Bandar detector shows distribution" in out
    assert "Flow ratio" in out
    assert "0.0" in out
    assert "lacks foreign-flow" in out
    assert "confirmation" in out
    assert "recent signal-window accumulation is occurring" not in out
