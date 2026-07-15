"""Tests for the accumulation-screen result projector (S2)."""

import pytest

from src.application.dto.accumulation_screen import (
    AccumulationCandidate,
    AccumulationScreenResponse,
)
from datetime import date
from decimal import Decimal

from src.application.services.broker_quality import BrokerQualitySnapshot
from src.application.services.screen_accum_result_projector import (
    ScreenAccumProjectionError,
    project_multi_screen_result,
    project_single_screen_result,
    validate_multi_window_request,
)


def _candidate(**overrides) -> AccumulationCandidate:
    values = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=5 / 7,
        total_net_value=Decimal("10000000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("1030"),
        current_price=Decimal("1000"),
        vwap_discount_pct=3.0,
        rsi=55.0,
        trend="SIDE",
        foreign_flow_score=70.0,
        top_brokers=None,
        institutional_flag=False,
    )
    values.update(overrides)
    return AccumulationCandidate(**values)


def _response(candidates, window_days=7) -> AccumulationScreenResponse:
    return AccumulationScreenResponse(
        candidates=candidates,
        screened_at=date(2026, 7, 14),
        window_days=window_days,
        total_tickers_checked=len(candidates),
        tickers_skipped=0,
        provider="test",
    )


# ---------------------------------------------------------------------------
# Single-window projection
# ---------------------------------------------------------------------------


def test_single_projection_applies_vwap_only():
    underwater = _candidate(ticker="A", vwap_discount_pct=5.0)
    not_underwater = _candidate(ticker="B", vwap_discount_pct=-2.0)
    response = _response([underwater, not_underwater])

    projection = project_single_screen_result(
        response,
        vwap_only=True,
        squeeze_only=False,
        top=10,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
    )

    assert [c.ticker for c in projection.candidates] == ["A"]
    assert projection.raw_candidate_count == 2
    assert projection.projected_candidate_count == 1
    assert projection.applied_filters.vwap_only is True


def test_single_projection_applies_min_streak():
    keep = _candidate(ticker="A", consecutive_streak=5)
    drop = _candidate(ticker="B", consecutive_streak=1)
    response = _response([keep, drop])

    projection = project_single_screen_result(
        response,
        vwap_only=False,
        squeeze_only=False,
        top=10,
        min_streak=3,
        coiled_spring_bb_pctile=0.20,
    )

    assert [c.ticker for c in projection.candidates] == ["A"]
    assert projection.raw_candidate_count == 2
    assert projection.applied_filters.min_streak == 3


def test_single_projection_counts_before_filter_is_pre_min_streak():
    """raw_candidate_count must reflect the screen response before ANY
    projector filter, including min_streak — not just before vwap/squeeze."""
    candidates = [_candidate(ticker=f"T{i}", consecutive_streak=0) for i in range(4)]
    response = _response(candidates)

    projection = project_single_screen_result(
        response,
        vwap_only=False,
        squeeze_only=False,
        top=10,
        min_streak=5,
        coiled_spring_bb_pctile=0.20,
    )

    assert projection.raw_candidate_count == 4
    assert projection.projected_candidate_count == 0


def test_single_projection_applies_squeeze_only():
    tight = _candidate(ticker="A", bb_width_pctile=0.10)
    loose = _candidate(ticker="B", bb_width_pctile=0.50)
    response = _response([tight, loose])

    projection = project_single_screen_result(
        response,
        vwap_only=False,
        squeeze_only=True,
        top=10,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
    )

    assert [c.ticker for c in projection.candidates] == ["A"]


def test_single_projection_applies_top_after_filters():
    candidates = [_candidate(ticker=f"T{i}", vwap_discount_pct=5.0) for i in range(5)]
    response = _response(candidates)

    projection = project_single_screen_result(
        response,
        vwap_only=True,
        squeeze_only=False,
        top=2,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
    )

    assert projection.projected_candidate_count == 2
    assert projection.raw_candidate_count == 5


def test_single_projection_data_as_of_from_candidates():
    c = _candidate(
        latest_candle_date=date(2026, 7, 10),
        latest_broker_date=date(2026, 7, 9),
    )
    response = _response([c])

    projection = project_single_screen_result(
        response,
        vwap_only=False,
        squeeze_only=False,
        top=10,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
    )

    assert projection.data_as_of["latest_candle_date"] == "2026-07-10"
    assert projection.data_as_of["latest_broker_date"] == "2026-07-09"


# ---------------------------------------------------------------------------
# Multi-window projection
# ---------------------------------------------------------------------------


def test_multi_projection_applies_squeeze_only():
    tight = _candidate(ticker="A", bb_width_pctile=0.10)
    loose = _candidate(ticker="B", bb_width_pctile=0.50)
    multi_results = {
        7: _response([tight, loose], window_days=7),
        30: _response([tight, loose], window_days=30),
    }

    projection = project_multi_screen_result(
        multi_results,
        broker_quality=None,
        windows=[7, 30],
        top=10,
        sort_by="avg",
        squeeze_only=True,
        coiled_spring_min_foreign_flow_score=50.0,
        coiled_spring_bb_pctile=0.20,
    )

    assert [row.ticker for row in projection.rows] == ["A"]
    assert projection.raw_ticker_count == 2
    assert projection.projected_row_count == 1


def test_multi_projection_applies_sort_by_window_label():
    a = _candidate(ticker="A", foreign_flow_score=90.0)
    b = _candidate(ticker="B", foreign_flow_score=10.0)
    a30 = _candidate(ticker="A", foreign_flow_score=10.0)
    b30 = _candidate(ticker="B", foreign_flow_score=90.0)
    multi_results = {
        7: _response([a, b], window_days=7),
        30: _response([a30, b30], window_days=30),
    }

    projection = project_multi_screen_result(
        multi_results,
        broker_quality=None,
        windows=[7, 30],
        top=10,
        sort_by="30s",
        squeeze_only=False,
        coiled_spring_min_foreign_flow_score=50.0,
        coiled_spring_bb_pctile=0.20,
    )

    assert [row.ticker for row in projection.rows] == ["B", "A"]


def test_multi_projection_applies_top():
    candidates = [_candidate(ticker=f"T{i}", foreign_flow_score=float(i)) for i in range(5)]
    multi_results = {7: _response(candidates, window_days=7)}

    projection = project_multi_screen_result(
        multi_results,
        broker_quality=None,
        windows=[7],
        top=2,
        sort_by="avg",
        squeeze_only=False,
        coiled_spring_min_foreign_flow_score=50.0,
        coiled_spring_bb_pctile=0.20,
    )

    assert projection.raw_ticker_count == 5
    assert projection.projected_row_count == 2


def test_multi_projection_includes_broker_quality():
    c = _candidate(ticker="A")
    multi_results = {7: _response([c], window_days=7)}
    quality = {
        "A": BrokerQualitySnapshot(
            label="smart+",
            smart_flow=Decimal("100"),
            noise_flow=Decimal("0"),
            neutral_flow=Decimal("0"),
            sessions=5,
            through_date=date(2026, 7, 14),
            source="stockbit",
        )
    }

    projection = project_multi_screen_result(
        multi_results,
        broker_quality=quality,
        windows=[7],
        top=10,
        sort_by="avg",
        squeeze_only=False,
        coiled_spring_min_foreign_flow_score=50.0,
        coiled_spring_bb_pctile=0.20,
    )

    assert projection.rows[0].broker_quality is quality["A"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_sort_by_fails():
    with pytest.raises(ScreenAccumProjectionError, match="Invalid --sort-by"):
        validate_multi_window_request([7, 30], "banana")


def test_duplicate_windows_fail():
    with pytest.raises(ScreenAccumProjectionError, match="Duplicate windows"):
        validate_multi_window_request([7, 7, 30], "avg")


def test_empty_windows_fail():
    with pytest.raises(ScreenAccumProjectionError, match="At least one window"):
        validate_multi_window_request([], "avg")


def test_window_specific_sort_by_fails_if_window_absent():
    with pytest.raises(ScreenAccumProjectionError, match="not in the resolved windows"):
        validate_multi_window_request([30, 90], "7s")


def test_avg_and_max_are_always_valid():
    validate_multi_window_request([7, 30], "avg")
    validate_multi_window_request([7, 30], "max")


def test_project_multi_screen_result_raises_on_invalid_sort_by():
    c = _candidate(ticker="A")
    multi_results = {7: _response([c], window_days=7)}

    with pytest.raises(ScreenAccumProjectionError):
        project_multi_screen_result(
            multi_results,
            broker_quality=None,
            windows=[7],
            top=10,
            sort_by="30s",
            squeeze_only=False,
            coiled_spring_min_foreign_flow_score=50.0,
            coiled_spring_bb_pctile=0.20,
        )


# ---------------------------------------------------------------------------
# S3 — freshness computed once by the projector, shared by table and JSON
# ---------------------------------------------------------------------------


def test_single_projection_attaches_freshness_to_each_projected_candidate():
    c = _candidate(
        ticker="A",
        latest_candle_date=date(2026, 7, 13),
        latest_broker_date=date(2026, 7, 13),
    )
    response = _response([c])

    projection = project_single_screen_result(
        response,
        vwap_only=False,
        squeeze_only=False,
        top=10,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
    )

    (result_candidate,) = projection.candidates
    assert result_candidate.freshness is not None
    assert result_candidate.freshness.candle_as_of == date(2026, 7, 13)
    assert result_candidate.freshness.broker_as_of == date(2026, 7, 13)
    assert result_candidate.freshness.sources_aligned is True


def test_single_projection_does_not_attach_freshness_to_filtered_out_candidates():
    kept = _candidate(ticker="A", vwap_discount_pct=5.0)
    dropped = _candidate(ticker="B", vwap_discount_pct=-2.0)
    response = _response([kept, dropped])

    project_single_screen_result(
        response,
        vwap_only=True,
        squeeze_only=False,
        top=10,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
    )

    assert dropped.freshness is None


def test_multi_projection_attaches_freshness_to_projected_window_candidates():
    c = _candidate(
        ticker="A",
        latest_candle_date=date(2026, 7, 13),
        latest_broker_date=date(2026, 7, 13),
    )
    multi_results = {7: _response([c], window_days=7)}

    projection = project_multi_screen_result(
        multi_results,
        broker_quality=None,
        windows=[7],
        top=10,
        sort_by="avg",
        squeeze_only=False,
        coiled_spring_min_foreign_flow_score=50.0,
        coiled_spring_bb_pctile=0.20,
    )

    (row,) = projection.rows
    result_candidate = row.candidates_by_window[7]
    assert result_candidate.freshness is not None
    assert result_candidate.freshness.candle_as_of == date(2026, 7, 13)
    assert result_candidate.freshness.broker_as_of == date(2026, 7, 13)
    assert result_candidate.freshness.alignment_state.value == "ALIGNED"


def test_multi_projection_does_not_attach_freshness_to_squeeze_filtered_out_candidates():
    tight = _candidate(
        ticker="A",
        bb_width_pctile=0.10,
        latest_candle_date=date(2026, 7, 13),
        latest_broker_date=date(2026, 7, 13),
    )
    loose = _candidate(
        ticker="B",
        bb_width_pctile=0.50,
        latest_candle_date=date(2026, 7, 13),
        latest_broker_date=date(2026, 7, 13),
    )
    multi_results = {7: _response([tight, loose], window_days=7)}

    projection = project_multi_screen_result(
        multi_results,
        broker_quality=None,
        windows=[7],
        top=10,
        sort_by="avg",
        squeeze_only=True,
        coiled_spring_min_foreign_flow_score=50.0,
        coiled_spring_bb_pctile=0.20,
    )

    assert [row.ticker for row in projection.rows] == ["A"]
    assert tight.freshness is not None
    assert loose.freshness is None
