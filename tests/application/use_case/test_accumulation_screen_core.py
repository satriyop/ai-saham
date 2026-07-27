"""Core screening behavior tests for foreign accumulation screening."""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationDerivedFeaturePolicy,
    AccumulationScreenRequest,
)
from src.application.services.accumulation_multi_window_pattern import (
    classify_multi_window_pattern,
)
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.services.signal_engine import SignalEngine
from src.application.services.signal_engine_config import SignalEngineConfig
from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenUseCase,
)
from src.domain.entities.broker_flow import BrokerSummary
from tests.application.use_case.accumulation_screen_fixtures import (
    FakeRulesLoader,
    MockBrokerRepository,
    MockMarketRepository,
    RecordingInsiderProvider,
    _candle,
    _summary,
    _weekdays,
    make_signal_evidence_execution_context,
)


def _make_candidate(score: float, bb_width_pctile: float | None = None) -> AccumulationCandidate:
    return AccumulationCandidate(
        ticker="TEST",
        window_days=7,
        net_buy_days=4,
        total_days=5,
        net_buy_ratio=0.8,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1000"),
        current_price=Decimal("1000"),
        vwap_discount_pct=0.0,
        rsi=50.0,
        trend="UP",
        accum_score=score,
        top_brokers=None,
        institutional_flag=False,
        bb_width_pctile=bb_width_pctile,
    )


_WINDOWS = [7, 30, 90]
_MIN_SCORE = 60.0
_BB_PCTILE = 0.20


def test_screen_window_uses_latest_broker_sessions_not_calendar_days():
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )

    candidate = response.candidates[0]
    assert candidate.total_days == 7
    assert candidate.net_buy_days == 7
    assert candidate.consecutive_streak == 7
    assert candidate.window_days == 7


def test_screen_passes_as_of_date_to_insider_provider():
    session_dates = _weekdays(date(2026, 1, 1), 9)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]
    insider_provider = RecordingInsiderProvider()

    use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        insider_activity_provider=insider_provider,
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )

    assert insider_provider.calls
    assert insider_provider.calls[0]["ticker"] == "BBCA"
    assert insider_provider.calls[0]["action_type"] == "ALL"
    assert insider_provider.calls[0]["as_of_date"] == as_of


def test_screen_ignores_unsafe_broker_summary_rows():
    session_dates = _weekdays(date(2026, 1, 1), 8)
    as_of = session_dates[-1]
    candles = [
        _candle("BBCA", date(2025, 12, 1) + timedelta(days=i), Decimal("100")) for i in range(45)
    ]
    valid_summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates[:-1]]
    unsafe_latest = BrokerSummary(
        ticker="BBCA",
        date=session_dates[-1],
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=Decimal("999999999999"),
        foreign_sell_value=Decimal("0"),
        foreign_buy_lot=10_000,
        foreign_sell_lot=0,
        total_value=Decimal("0"),
        total_lot=0,
    )

    use_case = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository([*valid_summaries, unsafe_latest]),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    response = use_case.execute(
        AccumulationScreenRequest(
            tickers=["BBCA"],
            window_days=7,
            min_net_buy_days=1,
            as_of_date=as_of,
        ),
        execution_context=make_signal_evidence_execution_context(as_of),
    )

    candidate = response.candidates[0]
    assert candidate.total_days == 7
    assert candidate.net_buy_days == 7
    assert candidate.total_net_value == sum(
        (s.foreign_net_value for s in valid_summaries),
        Decimal("0"),
    )


def test_screen_uses_derived_feature_policy_for_trend_threshold():
    session_dates = _weekdays(date(2026, 1, 1), 7)
    as_of = session_dates[-1]
    candle_dates = _weekdays(date(2025, 12, 1), 25)
    candles = [_candle("BBCA", day, Decimal("100")) for day in candle_dates[:-1]] + [
        _candle("BBCA", candle_dates[-1], Decimal("103"))
    ]
    summaries = [_summary("BBCA", day, Decimal("110")) for day in session_dates]

    loose_threshold = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        derived_feature_policy=AccumulationDerivedFeaturePolicy(
            trend_sma_period=20,
            trend_threshold_pct=5.0,
        ),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )
    strict_threshold = AccumulationScreenUseCase(
        indicator_registry=IndicatorRegistry(),
        broker_repository=MockBrokerRepository(summaries),
        market_repository=MockMarketRepository(candles),
        rules_loader=FakeRulesLoader(),
        derived_feature_policy=AccumulationDerivedFeaturePolicy(
            trend_sma_period=20,
            trend_threshold_pct=2.0,
        ),
        signal_engine=SignalEngine(config=SignalEngineConfig()),
    )

    request = AccumulationScreenRequest(
        tickers=["BBCA"],
        window_days=7,
        min_net_buy_days=1,
        as_of_date=as_of,
    )

    context = make_signal_evidence_execution_context(as_of)
    assert loose_threshold.execute(request, execution_context=context).candidates[0].trend == "SIDE"
    assert strict_threshold.execute(request, execution_context=context).candidates[0].trend == "UP"


def test_classify_all_windows_hot_is_sustained():
    candidates = {w: _make_candidate(score=70.0) for w in _WINDOWS}
    assert (
        classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "sustained"
    )


def test_classify_only_short_window_hot_is_fresh_rotation():
    candidates = {
        7: _make_candidate(score=70.0),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=40.0),
    }
    assert (
        classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE)
        == "fresh rotation"
    )


def test_classify_only_long_window_hot_is_long_term_only():
    candidates = {
        7: _make_candidate(score=40.0),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=70.0),
    }
    assert (
        classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE)
        == "long-term only"
    )


def test_classify_short_and_long_hot_but_not_all_is_building():
    # "building" fires when min hot AND max hot but not all windows hot.
    # If max is NOT hot, "fresh rotation" takes priority (checked first).
    windows = [7, 30, 90, 180]
    candidates = {
        7: _make_candidate(score=70.0),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=40.0),
        180: _make_candidate(score=70.0),
    }
    assert classify_multi_window_pattern(windows, candidates, _MIN_SCORE, _BB_PCTILE) == "building"


def test_classify_coiled_spring_when_squeeze_and_high_score():
    candidates = {
        7: _make_candidate(score=70.0, bb_width_pctile=0.10),
        30: _make_candidate(score=40.0),
        90: _make_candidate(score=40.0),
    }
    assert (
        classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE)
        == "coiled spring"
    )


def test_classify_weak_when_no_windows_hot():
    candidates = {w: _make_candidate(score=30.0) for w in _WINDOWS}
    assert classify_multi_window_pattern(_WINDOWS, candidates, _MIN_SCORE, _BB_PCTILE) == "weak"


def test_accumulation_screen_use_case_requires_signal_engine():
    """HIGH-2 Finding 1: signal_engine has no default and no
    `signal_engine or SignalEngine()` fallback — omitting it must fail the
    normal Python constructor call, not silently construct an unconfigured
    engine that bypasses the configured authority-coverage floor."""
    import pytest

    with pytest.raises(TypeError):
        AccumulationScreenUseCase(
            broker_repository=MockBrokerRepository([]),
            market_repository=MockMarketRepository([]),
            indicator_registry=IndicatorRegistry(),
            rules_loader=FakeRulesLoader(),
        )
