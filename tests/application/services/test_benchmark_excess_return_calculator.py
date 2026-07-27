"""Tests for BenchmarkExcessReturnCalculator.

Layer: Application (pure calculator, no IO). Tests exercise the public
`calculate()` API only.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.services.benchmark_excess_return_calculator import (
    BenchmarkExcessReturnCalculator,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.benchmark_excess_return import BenchmarkExcessReturnStatus


def _candle(ticker: str, day: date, close: Decimal) -> Candle:
    return Candle(
        ticker=ticker,
        date=day,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
    )


def _days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


def test_positive_excess_return_20_session():
    """Ticker rises 20% over 20 sessions while IHSG rises 5% -> excess = +15.0."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 21)
    as_of = dates[-1]

    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("100") if i == 0 else Decimal("120")) for i in range(21)
    ]
    benchmark_candles = [
        _candle("IHSG", dates[i], Decimal("100") if i == 0 else Decimal("105")) for i in range(21)
    ]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )
    window = result.excess_return_vs_ihsg_20_session

    assert window.status == BenchmarkExcessReturnStatus.AVAILABLE
    assert window.ticker_return_pct == pytest.approx(20.0)
    assert window.benchmark_return_pct == pytest.approx(5.0)
    assert window.excess_return_pct == pytest.approx(15.0)
    assert window.window_start == dates[0]
    assert window.window_end == dates[-1]
    assert window.common_session_count == 21
    assert window.benchmark == "IHSG"
    assert window.window_sessions == 20


def test_negative_excess_return_5_session():
    """Ticker falls 5% over 5 sessions while IHSG stays flat -> excess = -5.0."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 6)
    as_of = dates[-1]

    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("100") if i == 0 else Decimal("95")) for i in range(6)
    ]
    benchmark_candles = [_candle("IHSG", dates[i], Decimal("100")) for i in range(6)]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )
    window = result.excess_return_vs_ihsg_5_session

    assert window.status == BenchmarkExcessReturnStatus.AVAILABLE
    assert window.ticker_return_pct == pytest.approx(-5.0)
    assert window.benchmark_return_pct == pytest.approx(0.0)
    assert window.excess_return_pct == pytest.approx(-5.0)
    assert window.window_start == dates[0]
    assert window.window_end == dates[-1]


def test_5_session_requires_exactly_six_aligned_closes():
    """Five aligned closes (one short) -> UNAVAILABLE; six -> AVAILABLE."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 6)

    # Only 5 aligned dates (need 6 for a 5-session window).
    short_ticker = [_candle("BBCA", dates[i], Decimal("100")) for i in range(5)]
    short_benchmark = [_candle("IHSG", dates[i], Decimal("100")) for i in range(5)]
    short_result = calc.calculate(
        ticker_candles=short_ticker,
        benchmark_candles=short_benchmark,
        as_of_date=dates[4],
    )
    assert short_result.excess_return_vs_ihsg_5_session.status == (
        BenchmarkExcessReturnStatus.UNAVAILABLE
    )
    assert short_result.excess_return_vs_ihsg_5_session.common_session_count == 5

    # Exactly 6 aligned dates -> AVAILABLE.
    full_ticker = [_candle("BBCA", dates[i], Decimal("100")) for i in range(6)]
    full_benchmark = [_candle("IHSG", dates[i], Decimal("100")) for i in range(6)]
    full_result = calc.calculate(
        ticker_candles=full_ticker,
        benchmark_candles=full_benchmark,
        as_of_date=dates[5],
    )
    assert full_result.excess_return_vs_ihsg_5_session.status == (
        BenchmarkExcessReturnStatus.AVAILABLE
    )


def test_20_session_requires_exactly_21_aligned_closes():
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 21)

    short_ticker = [_candle("BBCA", dates[i], Decimal("100")) for i in range(20)]
    short_benchmark = [_candle("IHSG", dates[i], Decimal("100")) for i in range(20)]
    short_result = calc.calculate(
        ticker_candles=short_ticker,
        benchmark_candles=short_benchmark,
        as_of_date=dates[19],
    )
    assert short_result.excess_return_vs_ihsg_20_session.status == (
        BenchmarkExcessReturnStatus.UNAVAILABLE
    )
    assert short_result.excess_return_vs_ihsg_20_session.common_session_count == 20

    full_ticker = [_candle("BBCA", dates[i], Decimal("100")) for i in range(21)]
    full_benchmark = [_candle("IHSG", dates[i], Decimal("100")) for i in range(21)]
    full_result = calc.calculate(
        ticker_candles=full_ticker,
        benchmark_candles=full_benchmark,
        as_of_date=dates[20],
    )
    assert full_result.excess_return_vs_ihsg_20_session.status == (
        BenchmarkExcessReturnStatus.AVAILABLE
    )


def test_independently_missing_dates_are_aligned_before_calculation():
    """Ticker missing one date and IHSG missing a different date must both be
    excluded from the common-session set before the window is sliced."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 8)
    as_of = dates[-1]

    # Ticker is missing dates[2]; benchmark is missing dates[5].
    ticker_candles = [
        _candle("BBCA", d, Decimal("100") + Decimal(i)) for i, d in enumerate(dates) if i != 2
    ]
    benchmark_candles = [_candle("IHSG", d, Decimal("100")) for i, d in enumerate(dates) if i != 5]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )
    window = result.excess_return_vs_ihsg_5_session

    # Common aligned dates exclude both index 2 and index 5 -> 6 aligned dates
    # remain out of 8 calendar days, exactly enough for a 5-session window.
    assert window.status == BenchmarkExcessReturnStatus.AVAILABLE
    assert window.common_session_count == 6
    expected_common = sorted(set(dates) - {dates[2], dates[5]})
    assert window.window_start == expected_common[0]
    assert window.window_end == expected_common[-1]
    assert window.window_start not in (dates[2], dates[5])


def test_ticker_and_benchmark_window_dates_are_identical():
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 21)
    as_of = dates[-1]

    ticker_candles = [_candle("BBCA", d, Decimal("100") + Decimal(i)) for i, d in enumerate(dates)]
    benchmark_candles = [
        _candle("IHSG", d, Decimal("100") + Decimal(i) / 2) for i, d in enumerate(dates)
    ]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )

    for window in (
        result.excess_return_vs_ihsg_5_session,
        result.excess_return_vs_ihsg_20_session,
    ):
        assert window.status == BenchmarkExcessReturnStatus.AVAILABLE
        # Both legs of the return are computed over the exact same dates.
        assert window.window_start is not None
        assert window.window_end == as_of


def test_future_candles_are_ignored():
    """Candles dated after as_of_date must be excluded, even when their
    prices would clearly change the result if included."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 6)
    as_of = dates[-1]

    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("100") if i == 0 else Decimal("110")) for i in range(6)
    ]
    benchmark_candles = [_candle("IHSG", dates[i], Decimal("100")) for i in range(6)]

    future_dates = _days(as_of + timedelta(days=1), 3)
    future_ticker_candles = [_candle("BBCA", d, Decimal("10")) for d in future_dates]
    future_benchmark_candles = [_candle("IHSG", d, Decimal("500")) for d in future_dates]

    result_with_future = calc.calculate(
        ticker_candles=ticker_candles + future_ticker_candles,
        benchmark_candles=benchmark_candles + future_benchmark_candles,
        as_of_date=as_of,
    )
    result_without_future = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )

    with_future = result_with_future.excess_return_vs_ihsg_5_session
    without_future = result_without_future.excess_return_vs_ihsg_5_session
    assert with_future.excess_return_pct == pytest.approx(without_future.excess_return_pct)
    assert with_future.excess_return_pct == pytest.approx(10.0)
    assert with_future.window_end == as_of


def test_zero_base_close_is_unavailable():
    """Base close (window sessions before latest) exactly 0 on either side ->
    UNAVAILABLE with zero_base_close reason, not a division error."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 6)
    as_of = dates[-1]

    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("0") if i == 0 else Decimal("100")) for i in range(6)
    ]
    benchmark_candles = [_candle("IHSG", dates[i], Decimal("100")) for i in range(6)]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )
    window = result.excess_return_vs_ihsg_5_session
    assert window.status == BenchmarkExcessReturnStatus.UNAVAILABLE
    assert window.unavailable_reason == "zero_base_close"
    assert window.excess_return_pct is None

    benchmark_candles_zero = [
        _candle("IHSG", dates[i], Decimal("0") if i == 0 else Decimal("100")) for i in range(6)
    ]
    ticker_candles_ok = [_candle("BBCA", dates[i], Decimal("100")) for i in range(6)]

    result2 = calc.calculate(
        ticker_candles=ticker_candles_ok,
        benchmark_candles=benchmark_candles_zero,
        as_of_date=as_of,
    )
    window2 = result2.excess_return_vs_ihsg_5_session
    assert window2.status == BenchmarkExcessReturnStatus.UNAVAILABLE
    assert window2.unavailable_reason == "zero_base_close"


def test_conflicting_duplicate_candles_fail_closed():
    """Two candles for the same date with different closes must not be
    silently resolved to one of the values -> both horizons UNAVAILABLE."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 21)
    as_of = dates[-1]

    ticker_candles = [_candle("BBCA", d, Decimal("100")) for d in dates]
    # Duplicate row for dates[10] with a conflicting close.
    ticker_candles.append(_candle("BBCA", dates[10], Decimal("999")))
    benchmark_candles = [_candle("IHSG", d, Decimal("100")) for d in dates]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )

    for window in (
        result.excess_return_vs_ihsg_5_session,
        result.excess_return_vs_ihsg_20_session,
    ):
        assert window.status == BenchmarkExcessReturnStatus.UNAVAILABLE
        assert window.unavailable_reason == "conflicting_duplicate_candles"
        assert window.excess_return_pct is None

    # Duplicate row with the SAME close is not a conflict.
    harmless_ticker_candles = [_candle("BBCA", d, Decimal("100")) for d in dates]
    harmless_ticker_candles.append(_candle("BBCA", dates[10], Decimal("100")))
    harmless_result = calc.calculate(
        ticker_candles=harmless_ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )
    assert harmless_result.excess_return_vs_ihsg_20_session.status == (
        BenchmarkExcessReturnStatus.AVAILABLE
    )


def test_horizons_available_independently():
    """5-session data can be sufficient while 20-session data is not, and
    vice versa — each horizon's status is computed independently."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 6)
    as_of = dates[-1]

    # Only 6 aligned dates: enough for 5-session, not for 20-session.
    ticker_candles = [_candle("BBCA", d, Decimal("100")) for d in dates]
    benchmark_candles = [_candle("IHSG", d, Decimal("100")) for d in dates]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )

    assert result.excess_return_vs_ihsg_5_session.status == (BenchmarkExcessReturnStatus.AVAILABLE)
    assert result.excess_return_vs_ihsg_20_session.status == (
        BenchmarkExcessReturnStatus.UNAVAILABLE
    )


def test_common_session_count_reports_window_sessions_plus_one_for_available_record():
    """A test with more than 21 aligned closes proving the 5-session record
    says 6 and the 20-session record says 21."""
    calc = BenchmarkExcessReturnCalculator()
    dates = _days(date(2026, 1, 1), 50)
    as_of = dates[-1]

    # 50 aligned closes
    ticker_candles = [_candle("BBCA", d, Decimal("100")) for d in dates]
    benchmark_candles = [_candle("IHSG", d, Decimal("100")) for d in dates]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )

    r5 = result.excess_return_vs_ihsg_5_session
    r20 = result.excess_return_vs_ihsg_20_session

    assert r5.status == BenchmarkExcessReturnStatus.AVAILABLE
    assert r5.common_session_count == 6

    assert r20.status == BenchmarkExcessReturnStatus.AVAILABLE
    assert r20.common_session_count == 21
