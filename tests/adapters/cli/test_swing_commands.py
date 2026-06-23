"""Tests for swing command helper logic."""

import logging
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

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
    FOREIGN_BOUNCE_PRESET,
    DataFreshness,
    PresetEvaluation,
    PresetGate,
    _auto_refresh_swing_data,
    _build_data_freshness,
    _evaluate_foreign_bounce,
    _fetch_swing_sentiment,
    _print_swing_output,
)
from src.adapters.cli.analyze_swing_display import (
    format_failed_gates_summary as _format_failed_gates_summary,
)
from src.adapters.cli.main import app
from src.application.use_case.accumulation_screen_use_case import AccumulationCandidate
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType

runner = CliRunner()


def _build_broker_detail(*args, **kwargs):
    return _build_broker_detail_base(
        *args,
        **kwargs,
        smart_money_brokers=swing_cli.SMART_MONEY_BROKERS,
        noise_brokers=swing_cli.NOISE_BROKERS,
        broker_weights=swing_cli.BROKER_WEIGHTS,
        smart_share_threshold_pct=swing_cli._SC.smart_share_threshold_pct,
    )


class FakeRangeRepository:
    def __init__(self, date_range):
        self._date_range = date_range

    def get_date_range(self, ticker: str):
        return self._date_range


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


class FakeBrokerProvider:
    provider_name = "idx"


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
        "score": 70.0,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


def test_foreign_bounce_passes_all_gates():
    evaluation = _evaluate_foreign_bounce(_candidate())

    assert evaluation.name == FOREIGN_BOUNCE_PRESET
    assert evaluation.passed is True
    assert evaluation.classification == "ENTER"
    assert evaluation.failed_reasons == ()


def test_foreign_bounce_reports_failed_gates():
    evaluation = _evaluate_foreign_bounce(_candidate(score=70.0, trend="DOWN"))

    assert evaluation.passed is False
    assert evaluation.classification == "WATCH"
    assert any("trend" in reason for reason in evaluation.failed_reasons)


def test_failed_gates_summary_includes_all_failed_reasons():
    evaluation = _evaluate_foreign_bounce(
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
    evaluation = _evaluate_foreign_bounce(None)

    assert evaluation.passed is False
    assert evaluation.classification == "AVOID"


def test_data_freshness_reports_source_dates_and_lag_warnings():
    freshness = _build_data_freshness(
        ticker="BBCA",
        as_of_date=date(2026, 6, 15),
        market_repo=FakeRangeRepository((date(2026, 1, 1), date(2026, 6, 12))),
        broker_repo=FakeRangeRepository((date(2026, 1, 2), date(2026, 6, 10))),
        refresh_actions=(
            "candles=provider-no-new-data(latest=2026-06-12)",
            "broker(idx)=ERR:timeout",
        ),
    )

    assert freshness.candle_end == date(2026, 6, 12)
    assert freshness.broker_end == date(2026, 6, 10)
    assert any("Latest candle" in warning for warning in freshness.warnings)
    assert any("Latest broker flow" in warning for warning in freshness.warnings)
    assert any("differ" in warning for warning in freshness.warnings)
    assert any("Refresh issue" in warning for warning in freshness.warnings)
    assert freshness.to_dict()["refresh_actions"] == [
        "candles=provider-no-new-data(latest=2026-06-12)",
        "broker(idx)=ERR:timeout",
    ]
    assert freshness.to_dict()["broker_flow_through"] == "2026-06-10"


def test_data_freshness_does_not_warn_for_friday_data_on_sunday():
    freshness = _build_data_freshness(
        ticker="JPFA",
        as_of_date=date(2026, 6, 14),
        market_repo=FakeRangeRepository((date(2026, 1, 1), date(2026, 6, 12))),
        broker_repo=FakeRangeRepository((date(2026, 1, 1), date(2026, 6, 12))),
        refresh_actions=(
            "candles=cached-current",
            "broker(stockbit)=cached-current",
        ),
    )

    assert freshness.warnings == ()


def test_auto_refresh_swing_data_uses_update_provider_factory(monkeypatch, tmp_path):
    def fake_fetch_candles(**kwargs):
        assert kwargs["ticker"] == "JPFA"
        assert kwargs["days"] == 365
        assert kwargs["db_path"] == tmp_path / "data.db"
        assert kwargs["provider_name"] == "yahoo"
        assert kwargs["refresh"] is False
        return "cached-current"

    def fake_create_broker_provider(name):
        assert name is None
        return FakeBrokerProvider(), "idx"

    def fake_fetch_broker(**kwargs):
        assert kwargs["ticker"] == "JPFA"
        assert kwargs["days"] == 90
        assert kwargs["db_path"] == tmp_path / "data.db"
        assert kwargs["broker_provider"].provider_name == "idx"
        assert kwargs["refresh"] is False
        return "cached-current"

    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_commands._fetch_candles",
        fake_fetch_candles,
    )
    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_commands._create_broker_provider",
        fake_create_broker_provider,
    )
    monkeypatch.setattr(
        "src.adapters.cli.fetch_market_commands._fetch_broker",
        fake_fetch_broker,
    )

    assert _auto_refresh_swing_data(
        ticker="JPFA",
        db_path=tmp_path / "data.db",
        force_refresh=False,
    ) == (
        "candles=cached-current",
        "broker(idx)=cached-current",
    )


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
    assert buyer_rows["YP"]["broker_type"] == "local"
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
    preset = _evaluate_foreign_bounce(_candidate(score=75, trend="SIDE"))

    note = _build_broker_quality_note(detail, preset)

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
    preset = _evaluate_foreign_bounce(_candidate(score=68, trend="SIDE"))

    note = _build_broker_quality_note(detail, preset)

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
    preset = _evaluate_foreign_bounce(_candidate(score=75, trend="SIDE"))

    note = _build_broker_quality_note(detail, preset)

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
    preset = _evaluate_foreign_bounce(_candidate(score=75, trend="SIDE"))

    note = build_broker_quality_note(detail, preset, smart_sell_min_share_pct=15.0)

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
        "src.adapters.cli.analyze_swing_commands.SentimentFactory.create_news_provider",
        lambda: NoisyNewsProvider(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_commands.SentimentFactory.create_classifier",
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
        "src.adapters.cli.analyze_swing_commands.SentimentFactory.create_news_provider",
        lambda: NoisyNewsProvider(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.analyze_swing_commands.SentimentFactory.create_classifier",
        lambda use_ai=False: object(),
    )

    response, warning = _fetch_swing_sentiment("BBCA", sentiment_verbose=True)

    captured = capsys.readouterr()
    assert response is None
    assert warning == "Sentiment fetch failed: RAW_SENTIMENT_EXCEPTION"
    assert "RAW_SENTIMENT_STDOUT" in captured.out
    assert "RAW_SENTIMENT_STDERR" in captured.err


def test_swing_backtest_unknown_preset_error():
    result = runner.invoke(app, ["trade", "backtest-swing", "--preset", "unknown"])

    assert result.exit_code != 0
    assert "unknown swing preset" in result.output.lower()
    assert FOREIGN_BOUNCE_PRESET in result.output


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
    assert "MARKET REGIME" in result.output
    assert "RISK_OFF" in result.output


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
    preset = PresetEvaluation(
        name=FOREIGN_BOUNCE_PRESET,
        passed=False,
        classification="WATCH",
        gates=(
            PresetGate("score", True, "70.0", ">= 55"),
            PresetGate("trend", False, "DOWN", "SIDE"),
        ),
        failed_reasons=("trend: DOWN (required SIDE)",),
    )

    _print_swing_output(
        ticker="BBCA",
        today=date(2026, 6, 19),
        profile="balanced",
        strategy_name="foreign-accumulation",
        data_freshness=DataFreshness(
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
        preset_eval=preset,
        preset_sizing=None,
        broker_quality_note=None,
        market_regime=None,
        capital=None,
        backtest_result=None,
        sentiment_resp=None,
        sentiment_warning=None,
        sentiment_verbose=False,
        no_backtest=True,
        no_sentiment=True,
    )

    out = capsys.readouterr().out
    assert "Swing Decision - BBCA" in out
    assert "Decision" in out
    assert "Signal Snapshot" in out
    assert "PLAN" in out
    assert "WATCH only" in out
    assert "SUMMARY:" in out
