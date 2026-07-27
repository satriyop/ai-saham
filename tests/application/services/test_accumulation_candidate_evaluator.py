"""AccumulationCandidateEvaluator: consumed-row provenance and defensive
future/wrong-ticker filtering (ADR-041 CANONICAL-EVIDENCE-BOUNDARY).

A repository that ignores its own end_date/ticker filtering (a plausible
real bug — see codebase-known-pitfalls) must never be trusted blindly: the
evaluator itself must filter future and foreign-ticker rows out of both its
calculations and its provenance tuples.
"""

from datetime import date, timedelta
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationDerivedFeaturePolicy
from src.application.services.accumulation_candidate_evaluator import (
    AccumulationCandidateEvaluator,
    compute_bci_absorption_ratio,
)
from tests.application.use_case.accumulation_screen_fixtures import (
    MockBrokerRepositoryWithDaily,
    MockMarketRepository,
    _candle,
    _daily_flow,
    _summary,
    _weekdays,
)

TICKER = "BBCA"


class LeakyMarketRepository(MockMarketRepository):
    """A repository that ignores end_date/ticker scoping — simulates a real
    reader bug so the evaluator's own defensive filter is exercised, not the
    fake's honesty."""

    def get_candles(self, ticker, start_date=None, end_date=None):
        return sorted(self._candles, key=lambda c: c.date)


class LeakyBrokerRepository(MockBrokerRepositoryWithDaily):
    def get_broker_summaries(self, ticker, start_date=None, end_date=None):
        return sorted(self._summaries, key=lambda s: s.date)

    def get_broker_daily_flows(
        self, ticker, start_date=None, end_date=None, broker_codes=None, source=None
    ):
        return sorted(self._daily_flows, key=lambda f: (f.date, f.broker_code))


def _evaluator(market_repo, broker_repo) -> AccumulationCandidateEvaluator:
    return AccumulationCandidateEvaluator(
        broker_repository=broker_repo,
        market_repository=market_repo,
        derived_feature_policy=AccumulationDerivedFeaturePolicy(),
    )


def test_future_candle_rows_excluded_from_calculations_and_provenance():
    session_dates = _weekdays(date(2026, 1, 1), 10)
    today = session_dates[-1]
    future_date = today + timedelta(days=3)

    candles = [_candle(TICKER, day, Decimal("100")) for day in session_dates]
    candles.append(_candle(TICKER, future_date, Decimal("9999")))
    summaries = [_summary(TICKER, day, Decimal("110")) for day in session_dates]

    result = _evaluator(LeakyMarketRepository(candles), LeakyBrokerRepository(summaries)).evaluate(
        ticker=TICKER,
        window_days=10,
        today=today,
        min_net_buy_days=1,
        rsi_period=14,
        sma_period=20,
    )

    assert result is not None
    assert all(c.date <= today for c in result.consumed_candles)
    assert future_date not in {c.date for c in result.consumed_candles}
    # The future close (9999) must not leak into current_price.
    assert result.candidate.current_price == Decimal("100")


def test_future_broker_summary_rows_excluded_from_calculations_and_provenance():
    session_dates = _weekdays(date(2026, 1, 1), 10)
    today = session_dates[-1]
    future_date = today + timedelta(days=3)

    candles = [_candle(TICKER, day, Decimal("100")) for day in session_dates]
    summaries = [_summary(TICKER, day, Decimal("110")) for day in session_dates]
    summaries.append(_summary(TICKER, future_date, Decimal("9999")))

    result = _evaluator(LeakyMarketRepository(candles), LeakyBrokerRepository(summaries)).evaluate(
        ticker=TICKER,
        window_days=10,
        today=today,
        min_net_buy_days=1,
        rsi_period=14,
        sma_period=20,
    )

    assert result is not None
    assert all(s.date <= today for s in result.consumed_broker_summaries)
    assert future_date not in {s.date for s in result.consumed_broker_summaries}


def test_future_broker_daily_flow_rows_excluded_from_provenance():
    session_dates = _weekdays(date(2026, 1, 1), 10)
    today = session_dates[-1]
    future_date = today + timedelta(days=3)

    candles = [_candle(TICKER, day, Decimal("100")) for day in session_dates]
    summaries = [_summary(TICKER, day, Decimal("110")) for day in session_dates]
    daily_flows = [_daily_flow(TICKER, day, "AK", 100) for day in session_dates]
    daily_flows.append(_daily_flow(TICKER, future_date, "AK", 500))

    result = _evaluator(
        LeakyMarketRepository(candles), LeakyBrokerRepository(summaries, daily_flows)
    ).evaluate(
        ticker=TICKER,
        window_days=10,
        today=today,
        min_net_buy_days=1,
        rsi_period=14,
        sma_period=20,
    )

    assert result is not None
    assert all(f.date <= today for f in result.consumed_broker_daily_flows)
    assert future_date not in {f.date for f in result.consumed_broker_daily_flows}


def test_wrong_ticker_candle_rows_excluded():
    session_dates = _weekdays(date(2026, 1, 1), 10)
    today = session_dates[-1]

    candles = [_candle(TICKER, day, Decimal("100")) for day in session_dates]
    candles.append(_candle("ASII", today, Decimal("5000")))
    summaries = [_summary(TICKER, day, Decimal("110")) for day in session_dates]

    result = _evaluator(LeakyMarketRepository(candles), LeakyBrokerRepository(summaries)).evaluate(
        ticker=TICKER,
        window_days=10,
        today=today,
        min_net_buy_days=1,
        rsi_period=14,
        sma_period=20,
    )

    assert result is not None
    assert all(c.ticker == TICKER for c in result.consumed_candles)


def test_wrong_ticker_broker_summary_rows_excluded():
    session_dates = _weekdays(date(2026, 1, 1), 10)
    today = session_dates[-1]

    candles = [_candle(TICKER, day, Decimal("100")) for day in session_dates]
    summaries = [_summary(TICKER, day, Decimal("110")) for day in session_dates]
    summaries.append(_summary("ASII", today, Decimal("9999")))

    result = _evaluator(LeakyMarketRepository(candles), LeakyBrokerRepository(summaries)).evaluate(
        ticker=TICKER,
        window_days=10,
        today=today,
        min_net_buy_days=1,
        rsi_period=14,
        sma_period=20,
    )

    assert result is not None
    assert all(s.ticker == TICKER for s in result.consumed_broker_summaries)


def test_wrong_ticker_broker_daily_flow_rows_excluded():
    session_dates = _weekdays(date(2026, 1, 1), 10)
    today = session_dates[-1]

    candles = [_candle(TICKER, day, Decimal("100")) for day in session_dates]
    summaries = [_summary(TICKER, day, Decimal("110")) for day in session_dates]
    daily_flows = [_daily_flow(TICKER, day, "AK", 100) for day in session_dates]
    daily_flows.append(_daily_flow("ASII", today, "AK", 999))

    result = _evaluator(
        LeakyMarketRepository(candles), LeakyBrokerRepository(summaries, daily_flows)
    ).evaluate(
        ticker=TICKER,
        window_days=10,
        today=today,
        min_net_buy_days=1,
        rsi_period=14,
        sma_period=20,
    )

    assert result is not None
    assert all(f.ticker == TICKER for f in result.consumed_broker_daily_flows)


def test_consumed_rows_match_normal_honest_repository_behavior():
    """Non-adversarial sanity check: with an honest repository, consumed_*
    tuples equal exactly the window the candidate's own fields were computed
    from."""
    session_dates = _weekdays(date(2026, 1, 1), 10)
    today = session_dates[-1]
    candles = [_candle(TICKER, day, Decimal("100")) for day in session_dates]
    summaries = [_summary(TICKER, day, Decimal("110")) for day in session_dates]
    daily_flows = [_daily_flow(TICKER, day, "AK", 100) for day in session_dates]

    result = _evaluator(
        MockMarketRepository(candles),
        MockBrokerRepositoryWithDaily(summaries, daily_flows),
    ).evaluate(
        ticker=TICKER,
        window_days=10,
        today=today,
        min_net_buy_days=1,
        rsi_period=14,
        sma_period=20,
    )

    assert result is not None
    assert len(result.consumed_candles) == len(session_dates)
    assert len(result.consumed_broker_summaries) == len(session_dates)
    assert len(result.consumed_broker_daily_flows) == len(session_dates)
    assert result.candidate.latest_candle_date == today
    assert result.candidate.latest_broker_date == today


def test_compute_bci_absorption_ratio_none_when_aggregate_not_selling():
    assert (
        compute_bci_absorption_ratio(
            bci_tier1_net_value=Decimal("100"),
            total_net_value=Decimal("50"),
        )
        is None
    )
    assert (
        compute_bci_absorption_ratio(
            bci_tier1_net_value=Decimal("100"),
            total_net_value=Decimal("0"),
        )
        is None
    )


def test_compute_bci_absorption_ratio_when_aggregate_selling():
    assert (
        compute_bci_absorption_ratio(
            bci_tier1_net_value=Decimal("21000000"),
            total_net_value=Decimal("-70000000"),
        )
        == 0.3
    )
    assert (
        compute_bci_absorption_ratio(
            bci_tier1_net_value=Decimal("0"),
            total_net_value=Decimal("-100"),
        )
        == 0.0
    )
