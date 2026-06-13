"""Tests for swing command helper logic."""

import logging
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from src.adapters.cli.main import app
from src.adapters.cli.swing_commands import (
    FOREIGN_BOUNCE_PRESET,
    _build_data_freshness,
    _build_flow_detail,
    _evaluate_foreign_bounce,
    _fetch_swing_sentiment,
)
from src.application.use_case.accumulation_screen import AccumulationCandidate
from src.domain.entities.broker_flow import BrokerSummary

runner = CliRunner()


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


def _summary(day: date, buy: str, sell: str, total: str = "1000000000") -> BrokerSummary:
    net_value = Decimal(buy) - Decimal(sell)
    return BrokerSummary(
        ticker="BBCA",
        date=day,
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=Decimal(buy),
        foreign_sell_value=Decimal(sell),
        foreign_buy_lot=max(int(net_value), 0),
        foreign_sell_lot=max(-int(net_value), 0),
        total_value=Decimal(total),
        total_lot=1000,
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
    evaluation = _evaluate_foreign_bounce(
        _candidate(score=70.0, trend="DOWN")
    )

    assert evaluation.passed is False
    assert evaluation.classification == "WATCH"
    assert any("trend" in reason for reason in evaluation.failed_reasons)


def test_foreign_bounce_missing_accumulation_is_avoid():
    evaluation = _evaluate_foreign_bounce(None)

    assert evaluation.passed is False
    assert evaluation.classification == "AVOID"


def test_data_freshness_reports_source_dates_and_lag_warnings():
    freshness = _build_data_freshness(
        ticker="BBCA",
        as_of_date=date(2026, 6, 13),
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


def test_flow_detail_uses_latest_broker_sessions():
    detail = _build_flow_detail(
        ticker="BBCA",
        broker_repo=FakeBrokerSummaryRepository([
            _summary(date(2026, 6, 1), "120000000", "20000000"),
            _summary(date(2026, 6, 2), "10000000", "50000000"),
            _summary(date(2026, 6, 3), "80000000", "10000000"),
            _summary(date(2026, 6, 4), "90000000", "10000000"),
        ]),
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
        "src.adapters.cli.swing_commands.SentimentFactory.create_news_provider",
        lambda: NoisyNewsProvider(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.swing_commands.SentimentFactory.create_classifier",
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
        "src.adapters.cli.swing_commands.SentimentFactory.create_news_provider",
        lambda: NoisyNewsProvider(),
    )
    monkeypatch.setattr(
        "src.adapters.cli.swing_commands.SentimentFactory.create_classifier",
        lambda use_ai=False: object(),
    )

    response, warning = _fetch_swing_sentiment("BBCA", sentiment_verbose=True)

    captured = capsys.readouterr()
    assert response is None
    assert warning == "Sentiment fetch failed: RAW_SENTIMENT_EXCEPTION"
    assert "RAW_SENTIMENT_STDOUT" in captured.out
    assert "RAW_SENTIMENT_STDERR" in captured.err


def test_swing_backtest_unknown_preset_error():
    result = runner.invoke(app, ["swing", "backtest", "--preset", "unknown"])

    assert result.exit_code != 0
    assert "unknown swing preset" in result.output.lower()
    assert FOREIGN_BOUNCE_PRESET in result.output


def test_regime_command_accepts_explicit_ticker_with_empty_cache(tmp_path: Path):
    result = runner.invoke(
        app,
        [
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
            "swing",
            "backtest",
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
            "swing",
            "compare",
            "BBCA",
            "--variants",
            "baseline,unknown",
        ],
    )

    assert result.exit_code != 0
    assert "unknown" in result.output.lower()
    assert "baseline" in result.output
