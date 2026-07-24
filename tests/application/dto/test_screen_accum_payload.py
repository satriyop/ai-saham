"""Unit tests for application-owned screen accum JSON payload builders."""

from datetime import date

from src.application.dto.accumulation_screen import AccumulationScreenResponse
from src.application.dto.screen_accum_payload import (
    build_accum_multi_envelope,
    build_accum_single_envelope,
)
from src.application.services.screen_accum_result_projector import (
    project_multi_screen_result,
    project_single_screen_result,
)
from src.application.use_case.save_screen_watchlist_use_case import (
    SaveScreenWatchlistResult,
)
from tests.adapters.cli.screen_accum_test_fixtures import (
    _FAKE_EFFECTIVE_SESSION,
    _candidate,
)


def test_build_accum_single_envelope_ok_with_strategy_save_and_actions():
    response = AccumulationScreenResponse(
        candidates=[_candidate(ticker="BBCA"), _candidate(ticker="BBRI")],
        screened_at=date(2026, 6, 28),
        window_days=7,
        total_tickers_checked=2,
        tickers_skipped=0,
        provider="fake",
    )
    projection = project_single_screen_result(
        response,
        vwap_only=False,
        squeeze_only=False,
        top=20,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
        effective_session=_FAKE_EFFECTIVE_SESSION,
    )

    envelope = build_accum_single_envelope(
        universe_label="lq45",
        response=response,
        projection=projection,
        effective_session=_FAKE_EFFECTIVE_SESSION,
        warnings=("note",),
        strategy_name="test-strat",
        strategy_signals={"BBCA": "OPEN"},
        save_result=SaveScreenWatchlistResult(saved_count=2, name="morning"),
    )

    assert envelope["verb"] == "accum"
    assert envelope["status"] == "ok"
    assert envelope["subject"] == {"kind": "universe", "id": "LQ45"}
    assert envelope["scope"] == "single"
    assert envelope["window"] == {"days": 7}
    assert envelope["fetch_hint"] == "saham fetch market --universe lq45"

    data = envelope["data"]
    assert data["artifact_type"] == "accumulation_screen"
    assert data["partial_result"] is False
    assert data["warnings"] == ["note"]
    assert data["strategy_name"] == "test-strat"
    assert data["strategy_signals"] == {"BBCA": "OPEN"}
    assert data["saved_watchlist"] == {"name": "morning", "saved_count": 2}
    assert data["effective_session"]["analysis_as_of"] == "2026-06-28"
    assert any(a["command"] == "saham view BBCA" for a in data["related_actions"])
    assert any(
        a["command"] == "saham screen compare morning"
        for a in data["related_actions"]
    )


def test_build_accum_single_envelope_empty_status():
    response = AccumulationScreenResponse(
        candidates=[],
        screened_at=date(2026, 6, 28),
        window_days=7,
        total_tickers_checked=3,
        tickers_skipped=1,
        provider="fake",
    )
    projection = project_single_screen_result(
        response,
        vwap_only=False,
        squeeze_only=False,
        top=20,
        min_streak=0,
        coiled_spring_bb_pctile=0.20,
        effective_session=_FAKE_EFFECTIVE_SESSION,
    )

    envelope = build_accum_single_envelope(
        universe_label="2 tickers",
        response=response,
        projection=projection,
    )

    assert envelope["status"] == "empty"
    assert envelope["data"]["candidates"] == []
    assert envelope["data"]["partial_result"] is True
    assert envelope["data"]["related_actions"] == []


def test_build_accum_multi_envelope_ok():
    multi_results = {
        7: AccumulationScreenResponse(
            candidates=[_candidate(ticker="BBCA")],
            screened_at=date(2026, 6, 28),
            window_days=7,
            total_tickers_checked=1,
            tickers_skipped=0,
            provider="fake",
        ),
    }
    projection = project_multi_screen_result(
        multi_results,
        tracked_broker_flow={},
        windows=[7],
        top=20,
        sort_by="avg",
        squeeze_only=False,
        coiled_spring_min_accum_score=50.0,
        coiled_spring_bb_pctile=0.20,
        canonical_window=7,
        effective_session=_FAKE_EFFECTIVE_SESSION,
    )

    envelope = build_accum_multi_envelope(
        universe_label="lq45",
        projection=projection,
        multi_results=multi_results,
        effective_session=_FAKE_EFFECTIVE_SESSION,
        warnings=(),
    )

    assert envelope["status"] == "ok"
    assert envelope["scope"] == "multi"
    assert envelope["window"] is None
    data = envelope["data"]
    assert data["artifact_type"] == "accumulation_screen_multi"
    assert data["mode"] == "multi"
    assert "BBCA" in data["tickers"]
    assert any(a["command"] == "saham view BBCA" for a in data["related_actions"])


def test_build_accum_multi_envelope_empty_when_no_rows():
    multi_results = {
        7: AccumulationScreenResponse(
            candidates=[],
            screened_at=date(2026, 6, 28),
            window_days=7,
            total_tickers_checked=2,
            tickers_skipped=0,
            provider="fake",
        ),
    }
    projection = project_multi_screen_result(
        multi_results,
        tracked_broker_flow={},
        windows=[7],
        top=20,
        sort_by="avg",
        squeeze_only=False,
        coiled_spring_min_accum_score=50.0,
        coiled_spring_bb_pctile=0.20,
        canonical_window=7,
        effective_session=_FAKE_EFFECTIVE_SESSION,
    )

    envelope = build_accum_multi_envelope(
        universe_label="lq45",
        projection=projection,
        multi_results=multi_results,
    )

    assert envelope["status"] == "empty"
    assert envelope["data"]["tickers"] == {}
    assert envelope["data"]["related_actions"] == []
