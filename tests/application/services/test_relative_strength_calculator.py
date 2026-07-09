"""Tests for RelativeStrengthCalculator.

Layer: Application (pure calculator, no IO). Tests exercise the public
`calculate()` API only.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.services.relative_strength_calculator import (
    RelativeStrengthCalculator,
)
from src.domain.entities.candle import Candle


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


def test_positive_relative_strength_20d():
    """Ticker rises 20% over 20 sessions while IHSG rises 5% -> RS = +15.0."""
    calc = RelativeStrengthCalculator()
    dates = _days(date(2026, 1, 1), 21)
    as_of = dates[-1]

    # 21 candles -> closes[-21] is the base for a 20d window.
    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("100") if i == 0 else Decimal("120"))
        for i in range(21)
    ]
    benchmark_candles = [
        _candle("IHSG", dates[i], Decimal("100") if i == 0 else Decimal("105"))
        for i in range(21)
    ]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
        windows=(20,),
    )

    ticker_return_pct = (Decimal("120") - Decimal("100")) / Decimal("100") * 100
    benchmark_return_pct = (Decimal("105") - Decimal("100")) / Decimal("100") * 100
    expected = float(ticker_return_pct - benchmark_return_pct)

    assert result.rs_vs_ihsg_20d == pytest.approx(expected)
    assert result.rs_vs_ihsg_20d == pytest.approx(15.0)
    assert result.unavailable_reasons == ()


def test_negative_relative_strength_5d():
    """Ticker falls 5% over 5 sessions while IHSG stays flat -> RS = -5.0."""
    calc = RelativeStrengthCalculator()
    dates = _days(date(2026, 1, 1), 6)
    as_of = dates[-1]

    # 6 candles -> closes[-6] is the base for a 5d window.
    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("100") if i == 0 else Decimal("95"))
        for i in range(6)
    ]
    benchmark_candles = [_candle("IHSG", dates[i], Decimal("100")) for i in range(6)]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
        windows=(5,),
    )

    ticker_return_pct = (Decimal("95") - Decimal("100")) / Decimal("100") * 100
    benchmark_return_pct = Decimal("0")
    expected = float(ticker_return_pct - benchmark_return_pct)

    assert result.rs_vs_ihsg_5d == pytest.approx(expected)
    assert result.rs_vs_ihsg_5d == pytest.approx(-5.0)
    assert result.unavailable_reasons == ()


def test_insufficient_ticker_candles():
    """Fewer than window+1 ticker candles -> None + reason, even though
    benchmark candles are sufficient."""
    calc = RelativeStrengthCalculator()
    dates = _days(date(2026, 1, 1), 21)
    as_of = dates[-1]

    # Only 4 ticker candles (need 6 for a 5d window).
    ticker_candles = [_candle("BBCA", dates[i], Decimal("100")) for i in range(4)]
    benchmark_candles = [_candle("IHSG", dates[i], Decimal("100")) for i in range(21)]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
        windows=(5,),
    )

    assert result.rs_vs_ihsg_5d is None
    assert "insufficient_ticker_candles_5d" in result.unavailable_reasons


def test_insufficient_benchmark_candles():
    """Enough ticker candles but fewer than window+1 benchmark candles ->
    None + reason."""
    calc = RelativeStrengthCalculator()
    dates = _days(date(2026, 1, 1), 21)
    as_of = dates[-1]

    ticker_candles = [_candle("BBCA", dates[i], Decimal("100")) for i in range(21)]
    # Only 3 benchmark candles (need 6 for a 5d window).
    benchmark_candles = [_candle("IHSG", dates[i], Decimal("100")) for i in range(3)]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
        windows=(5,),
    )

    assert result.rs_vs_ihsg_5d is None
    assert "insufficient_benchmark_candles_5d" in result.unavailable_reasons


def test_zero_base_close():
    """Base close (N sessions before latest) exactly 0 on either side ->
    None + zero_base_close reason, not a division error."""
    calc = RelativeStrengthCalculator()
    dates = _days(date(2026, 1, 1), 6)
    as_of = dates[-1]

    # Ticker base close (closes[-6], i.e. dates[0]) is zero.
    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("0") if i == 0 else Decimal("100"))
        for i in range(6)
    ]
    benchmark_candles = [_candle("IHSG", dates[i], Decimal("100")) for i in range(6)]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
        windows=(5,),
    )

    assert result.rs_vs_ihsg_5d is None
    assert "zero_base_close_5d" in result.unavailable_reasons

    # Benchmark base close zero as well.
    benchmark_candles_zero = [
        _candle("IHSG", dates[i], Decimal("0") if i == 0 else Decimal("100"))
        for i in range(6)
    ]
    ticker_candles_ok = [_candle("BBCA", dates[i], Decimal("100")) for i in range(6)]

    result2 = calc.calculate(
        ticker_candles=ticker_candles_ok,
        benchmark_candles=benchmark_candles_zero,
        as_of_date=as_of,
        windows=(5,),
    )

    assert result2.rs_vs_ihsg_5d is None
    assert "zero_base_close_5d" in result2.unavailable_reasons


def test_ignores_candles_after_as_of_date():
    """Candles dated after as_of_date must be excluded from the calculation,
    even when their prices would clearly change the result if included."""
    calc = RelativeStrengthCalculator()
    dates = _days(date(2026, 1, 1), 6)
    as_of = dates[-1]  # last "in-window" date

    # Base ticker/benchmark series: 6 candles up to as_of (5d window).
    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("100") if i == 0 else Decimal("110"))
        for i in range(6)
    ]
    benchmark_candles = [_candle("IHSG", dates[i], Decimal("100")) for i in range(6)]

    # Extra future candles with prices that would swing the result heavily if
    # wrongly included (e.g. a ticker crash and benchmark spike after as_of).
    future_dates = _days(as_of + timedelta(days=1), 3)
    future_ticker_candles = [
        _candle("BBCA", d, Decimal("10")) for d in future_dates
    ]
    future_benchmark_candles = [
        _candle("IHSG", d, Decimal("500")) for d in future_dates
    ]

    result_with_future = calc.calculate(
        ticker_candles=ticker_candles + future_ticker_candles,
        benchmark_candles=benchmark_candles + future_benchmark_candles,
        as_of_date=as_of,
        windows=(5,),
    )
    result_without_future = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
        windows=(5,),
    )

    assert result_with_future.rs_vs_ihsg_5d == pytest.approx(
        result_without_future.rs_vs_ihsg_5d
    )
    assert result_with_future.rs_vs_ihsg_5d == pytest.approx(10.0)


def test_both_windows_computed_when_sufficient_data():
    """A single calculate() call with enough history populates both
    rs_vs_ihsg_5d and rs_vs_ihsg_20d simultaneously."""
    calc = RelativeStrengthCalculator()
    dates = _days(date(2026, 1, 1), 21)
    as_of = dates[-1]

    ticker_candles = [
        _candle("BBCA", dates[i], Decimal("100") + Decimal(i)) for i in range(21)
    ]
    benchmark_candles = [
        _candle("IHSG", dates[i], Decimal("100") + Decimal(i) / 2) for i in range(21)
    ]

    result = calc.calculate(
        ticker_candles=ticker_candles,
        benchmark_candles=benchmark_candles,
        as_of_date=as_of,
    )

    assert result.rs_vs_ihsg_5d is not None
    assert result.rs_vs_ihsg_20d is not None
    assert result.unavailable_reasons == ()
