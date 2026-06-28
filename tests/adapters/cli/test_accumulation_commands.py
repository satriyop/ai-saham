"""Tests for accumulation CLI helper logic."""

from datetime import date
from decimal import Decimal

from src.adapters.cli.screen_accum_commands import (
    _display_multi,
    _display_results,
)
from src.application.services.broker_quality import compute_broker_quality_batch
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from src.domain.entities.broker_flow import BrokerSummary, BrokerTransaction, BrokerType
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup


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
    buy: str,
    sell: str,
    broker_type: BrokerType = BrokerType.FOREIGN,
) -> BrokerTransaction:
    return BrokerTransaction(
        broker_code=code,
        broker_name=code,
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
    top_buyers: tuple[BrokerTransaction, ...] = (),
    top_sellers: tuple[BrokerTransaction, ...] = (),
) -> BrokerSummary:
    return BrokerSummary(
        ticker="BBCA",
        date=day,
        top_buyers=top_buyers,
        top_sellers=top_sellers,
        foreign_buy_value=Decimal("1000"),
        foreign_sell_value=Decimal("500"),
        foreign_buy_lot=10,
        foreign_sell_lot=5,
        total_value=Decimal("10000"),
        total_lot=100,
        source="stockbit",
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
        "accum_score": 70.0,
        "top_brokers": None,
        "institutional_flag": False,
        "avg_flow_ratio": 5.0,
    }
    values.update(overrides)
    return AccumulationCandidate(**values)


def test_screen_broker_quality_counts_local_noise_brokers():
    quality_batch = compute_broker_quality_batch(
        tickers=["BBCA"],
        broker_repo=FakeBrokerSummaryRepository([
            _summary(
                date(2026, 6, 12),
                top_buyers=(
                    _tx("YP", "100000000", "10000000", BrokerType.LOCAL),
                    _tx("XC", "70000000", "5000000", BrokerType.LOCAL),
                ),
                top_sellers=(_tx("AK", "5000000", "25000000"),),
            )
        ]),
        smart_money_brokers=[],
        noise_brokers=["YP", "XC"],
        as_of_date=date(2026, 6, 12),
    )

    quality = quality_batch.get("BBCA")
    assert quality is not None
    assert quality.label == "noise+"
    assert quality.noise_flow == Decimal("155000000")  # (100M-10M) + (70M-5M) = 90M + 65M
    assert quality.neutral_flow == Decimal("-20000000")  # AK: 5M buy - 25M sell = -20M
    assert quality.to_dict()["source"] == "stockbit"


def test_screen_broker_quality_marks_smart_selling_pressure():
    quality_batch = compute_broker_quality_batch(
        tickers=["BBCA"],
        broker_repo=FakeBrokerSummaryRepository([
            _summary(
                date(2026, 6, 12),
                top_buyers=(_tx("CC", "40000000", "5000000"),),
                top_sellers=(_tx("BK", "5000000", "90000000"),),
            )
        ]),
        smart_money_brokers=["BK"],
        noise_brokers=[],
        as_of_date=date(2026, 6, 12),
    )

    quality = quality_batch.get("BBCA")
    assert quality is not None
    assert quality.label == "smart-"
    assert quality.smart_flow == Decimal("-85000000")


def test_display_results_renders_rich_accumulation_panel(capsys):
    response = AccumulationScreenResponse(
        candidates=[_candidate()],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )

    _display_results(
        response=response,
        universe_label="lq45",
        top_n=10,
        show_top_broker=False,
        vwap_only=False,
        squeeze_only=False,
        include_explanation=False,
    )

    out = capsys.readouterr().out
    assert "Foreign Accumulation - LQ45" in out
    assert "Candidate Actions" in out
    assert "Verdict" not in out
    assert "BBCA" in out
    assert "Risk Status" in out
    assert "Rule Conf" not in out
    assert "Gate Conf" not in out
    assert "TechnicalGate is not evaluated by screen accum" in out
    assert "Scoring Definitions" not in out
    assert "Run Context" not in out


def test_display_results_renders_explanation_panels_when_requested(capsys):
    response = AccumulationScreenResponse(
        candidates=[_candidate()],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )

    _display_results(
        response=response,
        universe_label="lq45",
        top_n=10,
        show_top_broker=False,
        vwap_only=False,
        squeeze_only=False,
        include_explanation=True,
    )

    out = capsys.readouterr().out
    assert "Run Context" in out
    assert "Scoring Definitions" in out
    assert "Candidate Actions is the screen summary" in out
    assert "Swing trade watchlist" in out


def test_display_results_renders_blocked_risk_diagnostics(capsys):
    risk_assessment = RiskAssessment(
        sensitivity="balanced",
        rationale=("Piotroski F-Score 1 below threshold 3",),
        snapshot_date=date(2026, 6, 19),
        indicators=IndicatorSnapshot(
            date=date(2026, 6, 19),
            sma=Decimal("1000"),
            ema=Decimal("1010"),
            rsi=Decimal("55"),
        ),
        gate_triggered="FundamentalGate",
        gate_is_structural=True,
        gate_confidence=100,
    )
    trade_setup = TradeSetup(
        ticker="BBCA",
        snapshot_date=date(2026, 6, 19),
        action=SetupAction.BLOCKED_STRUCTURAL,
        signal_score=72,
        signal_score_raw=72,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=("FundamentalGate",),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="Blocked by FundamentalGate",
    )
    response = AccumulationScreenResponse(
        candidates=[
            _candidate(
                risk_assessment=risk_assessment,
                trade_setup=trade_setup,
            )
        ],
        screened_at=date(2026, 6, 19),
        window_days=7,
        total_tickers_checked=1,
        tickers_skipped=0,
        provider="stockbit",
    )

    _display_results(
        response=response,
        universe_label="lq45",
        top_n=10,
        show_top_broker=False,
        vwap_only=False,
        squeeze_only=False,
        include_explanation=False,
    )

    out = capsys.readouterr().out
    assert "Risk Status" in out
    assert "BLOCKED" in out
    assert "structural" in out
    assert "FundamentalGate" in out


def test_display_multi_renders_rich_accumulation_panel(capsys):
    results = {
        7: AccumulationScreenResponse(
            candidates=[_candidate(accum_score=72.0, window_days=7)],
            screened_at=date(2026, 6, 19),
            window_days=7,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="stockbit",
        ),
        30: AccumulationScreenResponse(
            candidates=[_candidate(accum_score=55.0, window_days=30)],
            screened_at=date(2026, 6, 19),
            window_days=30,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="stockbit",
        ),
    }

    _display_multi(
        results=results,
        universe_label="lq45",
        top_n=10,
        sort_by="avg",
        squeeze_only=False,
        screened_at=date(2026, 6, 19),
    )

    out = capsys.readouterr().out
    assert "Foreign Accumulation - LQ45" in out
    assert "multi-window" in out
    assert "BBCA" in out
    assert "Pattern" in out
    assert "Run Context" not in out
    assert "Broker Flow" in out
