from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.adapters.tui.controllers.accumulation_controller import (
    AccumulationController,
    AccumulationControllerPayload,
)
from src.adapters.tui.controllers.ticker_research_controller import (
    TickerResearchController,
)
from src.adapters.tui.presenters.accumulation_presenter import AccumulationPresenter
from src.adapters.tui.presenters.ticker_research_presenter import TickerResearchPresenter
from src.adapters.tui.research_capabilities import (
    build_accumulation_request,
    build_ticker_request,
)
from src.adapters.tui.state import ScreenStatus
from src.application.services.swing_analysis_input_collector import (
    SwingAnalysisDataUnavailable,
)
from src.infrastructure.config.app_config import AnalysisConfig, AppConfig

from .research_fixtures import single_result, ticker_response


def _dispatch(callback, *args):
    callback(*args)


def test_exact_accumulation_requests_preserve_resolved_ticker_list_identity():
    config = AppConfig(analysis=AnalysisConfig(universe="idx30"))
    tickers = ["BBRI", "BBCA"]
    single = build_accumulation_request(config, tickers, False)
    multi = build_accumulation_request(config, tickers, True)

    assert single.tickers is tickers
    assert single.universe_label == single.universe_name == "idx30"
    assert (single.window, single.min_streak, single.top, single.sort_by) == (7, 0, 20, "vwap")
    assert single.windows == [] and single.multi is False
    assert single.save_enabled is False and single.include_strategy_overlay is False
    assert multi.windows == [7, 30, 90] and multi.multi is True


def test_exact_ticker_request_is_local_only_and_preserves_ticker_verbatim():
    config = AppConfig()
    request = build_ticker_request(config, Path("local.db"), 30, "bBrI")
    assert request.ticker == "bBrI"
    assert request.window == 7 and request.flow_window == 30
    assert request.auto_refresh is False
    assert request.force_refresh is False
    assert request.include_sentiment is False
    assert request.with_market_context is False
    assert request.db_path == Path("local.db")


def test_projection_identity_order_and_no_reconstructed_equivalent():
    result = single_result()
    projection = result.single_projection
    payload = AccumulationControllerPayload(result, projection, False)
    view = AccumulationPresenter().present(payload)
    assert view.source is projection
    assert [row.ticker for row in view.rows] == ["BBRI", "BBCA"]

    reconstructed = replace(projection)
    with pytest.raises(ValueError, match="identity"):
        AccumulationControllerPayload(result, reconstructed, False)


def test_accumulation_late_result_is_ignored():
    results = iter((single_result(), single_result()))
    queued = []
    controller = AccumulationController(lambda multi: next(results))
    first = controller.begin()
    controller.execute_generation(
        first,
        multi=False,
        dispatch=lambda callback, *args: queued.append((callback, args)),
        listener=lambda state: None,
    )
    second = controller.begin()
    controller.execute_generation(
        second,
        multi=False,
        dispatch=lambda callback, *args: queued.append((callback, args)),
        listener=lambda state: None,
    )
    queued[1][0](*queued[1][1])
    second_payload = controller.state.payload
    queued[0][0](*queued[0][1])
    assert controller.state.generation == second
    assert controller.state.payload is second_payload


def test_ticker_unavailable_is_typed_and_other_errors_preserve_details():
    def unavailable(ticker):
        raise SwingAnalysisDataUnavailable(ticker)

    controller = TickerResearchController(unavailable)
    generation = controller.begin()
    controller.execute_generation(
        generation, ticker="BBRI", dispatch=_dispatch, listener=lambda state: None
    )
    assert controller.state.status is ScreenStatus.UNAVAILABLE
    assert controller.state.payload.reason == "BBRI"


def test_out_of_order_ticker_result_cannot_replace_newer_selection():
    responses = iter((ticker_response(ticker="BBRI"), ticker_response(ticker="BBCA")))
    queued = []
    controller = TickerResearchController(lambda ticker: next(responses))
    first = controller.begin()
    controller.execute_generation(
        first,
        ticker="BBRI",
        dispatch=lambda callback, *args: queued.append((callback, args)),
        listener=lambda state: None,
    )
    second = controller.begin()
    controller.execute_generation(
        second,
        ticker="BBCA",
        dispatch=lambda callback, *args: queued.append((callback, args)),
        listener=lambda state: None,
    )
    queued[1][0](*queued[1][1])
    newer = controller.state.payload
    queued[0][0](*queued[0][1])
    assert controller.state.generation == second
    assert controller.state.payload is newer


def test_ticker_response_identity_mismatch_fails_closed():
    controller = TickerResearchController(lambda ticker: ticker_response(ticker="BBCA"))
    generation = controller.begin()
    controller.execute_generation(
        generation,
        ticker="BBRI",
        dispatch=_dispatch,
        listener=lambda state: None,
    )
    assert controller.state.status is ScreenStatus.ERROR
    assert controller.state.error_type == "ValueError"
    assert "identity mismatch" in controller.state.error_message


def test_preview_never_enters_canonical_and_unavailable_has_no_action_fallback():
    presenter = TickerResearchPresenter()
    available = presenter.present(ticker_response())
    assert available.canonical.action == "CANONICAL_ONLY"
    assert ("action", "PREVIEW_ONLY") in available.preview

    unavailable = presenter.present(ticker_response(available=False))
    assert unavailable.canonical.signal_status == "UNAVAILABLE"
    assert unavailable.canonical.action is None
