"""Tests for the BenchmarkExcessReturn domain value object."""

from datetime import date

import pytest

from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)


def _available() -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=5,
        ticker_return_pct=3.25,
        benchmark_return_pct=1.10,
        excess_return_pct=2.15,
        window_start=date(2026, 6, 1),
        window_end=date(2026, 6, 8),
        common_session_count=6,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
        unavailable_reason=None,
    )


def _unavailable() -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn.unavailable(
        benchmark="IHSG",
        window_sessions=20,
        reason="insufficient_aligned_closes_20_session",
        common_session_count=12,
    )


def test_available_round_trips_every_field():
    original = _available()
    round_tripped = BenchmarkExcessReturn.from_dict(original.to_dict())

    assert round_tripped == original
    assert round_tripped.benchmark == "IHSG"
    assert round_tripped.window_sessions == 5
    assert round_tripped.ticker_return_pct == 3.25
    assert round_tripped.benchmark_return_pct == 1.10
    assert round_tripped.excess_return_pct == 2.15
    assert round_tripped.window_start == date(2026, 6, 1)
    assert round_tripped.window_end == date(2026, 6, 8)
    assert round_tripped.common_session_count == 6
    assert round_tripped.status == BenchmarkExcessReturnStatus.AVAILABLE
    assert round_tripped.unavailable_reason is None


def test_unavailable_round_trips_every_field():
    original = _unavailable()
    round_tripped = BenchmarkExcessReturn.from_dict(original.to_dict())

    assert round_tripped == original
    assert round_tripped.status == BenchmarkExcessReturnStatus.UNAVAILABLE
    assert round_tripped.unavailable_reason == "insufficient_aligned_closes_20_session"
    assert round_tripped.ticker_return_pct is None
    assert round_tripped.benchmark_return_pct is None
    assert round_tripped.excess_return_pct is None
    assert round_tripped.window_start is None
    assert round_tripped.window_end is None
    assert round_tripped.common_session_count == 12


def test_to_dict_status_is_plain_string():
    d = _available().to_dict()
    assert d["status"] == "AVAILABLE"
    d2 = _unavailable().to_dict()
    assert d2["status"] == "UNAVAILABLE"


def test_available_requires_component_and_excess_returns():
    with pytest.raises(ValueError):
        BenchmarkExcessReturn(
            benchmark="IHSG",
            window_sessions=5,
            ticker_return_pct=None,
            benchmark_return_pct=1.0,
            excess_return_pct=None,
            window_start=date(2026, 6, 1),
            window_end=date(2026, 6, 8),
            common_session_count=6,
            status=BenchmarkExcessReturnStatus.AVAILABLE,
            unavailable_reason=None,
        )


def test_unavailable_requires_reason():
    with pytest.raises(ValueError):
        BenchmarkExcessReturn(
            benchmark="IHSG",
            window_sessions=5,
            ticker_return_pct=None,
            benchmark_return_pct=None,
            excess_return_pct=None,
            window_start=None,
            window_end=None,
            common_session_count=0,
            status=BenchmarkExcessReturnStatus.UNAVAILABLE,
            unavailable_reason=None,
        )


def test_invalid_status_type_rejected():
    with pytest.raises(ValueError):
        BenchmarkExcessReturn(
            benchmark="IHSG",
            window_sessions=5,
            ticker_return_pct=None,
            benchmark_return_pct=None,
            excess_return_pct=None,
            window_start=None,
            window_end=None,
            common_session_count=0,
            status="AVAILABLE",  # type: ignore[arg-type]
            unavailable_reason=None,
        )
