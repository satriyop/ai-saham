"""Tests for Daily workspace refresh, modal confirmation, progress, and local reload.

Layer: Adapter
"""

from unittest.mock import MagicMock

from src.adapters.tui.controllers.daily_controller import DailyController
from src.adapters.tui.state import ScreenStatus
from src.application.use_case.daily_briefing_use_case import DailyBriefingResponse
from src.application.use_case.refresh_daily_workspace_use_case import (
    DailyWorkspaceRefreshPlan,
    RefreshDailyWorkspaceRequest,
    RefreshDailyWorkspaceResult,
)


def test_daily_controller_handles_refresh_generation_and_progress() -> None:
    mock_briefing = MagicMock(spec=DailyBriefingResponse)
    mock_briefing.universe_count = 45
    mock_briefing.regime = None
    mock_briefing.opening_candidates = []
    mock_briefing.market_wide_opening_observations = []
    mock_briefing.accumulation_candidates = []
    mock_briefing.daily_accumulation_candidates = [MagicMock()]
    mock_briefing.setup_lens_impact = None

    mock_refresh_res = MagicMock(spec=RefreshDailyWorkspaceResult)
    mock_refresh_res.briefing = mock_briefing
    mock_refresh_res.warnings = ()

    refresh_calls = []

    def fake_refresh(req, on_start=None, on_ticker_complete=None):
        refresh_calls.append(req)
        if on_start:
            on_start(MagicMock(ticker_count=45))
        if on_ticker_complete:
            on_ticker_complete("BBRI", 1, 45, "OK")
        return mock_refresh_res

    def fake_preview(req):
        return DailyWorkspaceRefreshPlan(
            universe=req.universe,
            resolved_ticker_count=45,
            history_days=30,
            components="ALL",
            candles_provider_label="yfinance",
            broker_provider_label="stockbit",
            include_meta=True,
            include_enrichment=True,
            include_calendar=True,
            local_write_disclosure="Disclosed cache write",
        )

    controller = DailyController(
        load_daily=lambda: mock_briefing,
        refresh_daily=fake_refresh,
        preview_daily=fake_preview,
    )

    req = RefreshDailyWorkspaceRequest(universe="lq45", days=30)
    plan = controller.get_preview(req)
    assert plan is not None
    assert plan.resolved_ticker_count == 45

    generation = controller.begin()
    events = []

    def dispatch(callback, *args):
        callback(*args)

    def listener(state):
        events.append(state)

    progress_events = []

    controller.execute_refresh_generation(
        generation,
        req,
        dispatch=dispatch,
        listener=listener,
        progress_callback=progress_events.append,
    )

    assert len(refresh_calls) == 1
    assert len(progress_events) == 2
    assert progress_events[0]["type"] == "start"
    assert progress_events[1]["type"] == "ticker"
    assert len(events) == 1
    assert events[0].status == ScreenStatus.READY
    assert events[0].payload == mock_refresh_res


def test_daily_controller_local_reload_does_not_call_refresher() -> None:
    mock_briefing = MagicMock(spec=DailyBriefingResponse)
    mock_briefing.universe_count = 45
    mock_briefing.daily_accumulation_candidates = [MagicMock()]
    mock_briefing.setup_lens_impact = None

    refresh_called = False

    def fake_refresh(req, **kwargs):
        nonlocal refresh_called
        refresh_called = True
        raise RuntimeError("Should not be called during local reload")

    controller = DailyController(
        load_daily=lambda: mock_briefing,
        refresh_daily=fake_refresh,
    )

    generation = controller.begin()
    events = []

    controller.execute_reload_generation(
        generation,
        dispatch=lambda callback, *args: callback(*args),
        listener=events.append,
    )

    assert not refresh_called
    assert len(events) == 1
    assert events[0].status == ScreenStatus.READY
    assert events[0].payload == mock_briefing
