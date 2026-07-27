"""Tests for Daily workspace refresh, modal confirmation, progress, and local reload.

Layer: Adapter
"""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from src.adapters.tui.controllers.daily_controller import DailyController
from src.adapters.tui.state import ScreenStatus
from src.application.use_case.daily_briefing_use_case import (
    DailyBriefingResponse,
    DailyBriefingUseCase,
)
from src.application.use_case.fetch_market_command_workflow_use_case import (
    FetchMarketCommandStartEvent,
    FetchMarketCommandWorkflowResult,
)
from src.application.use_case.fetch_market_refresh_use_case import (
    BrokerFetchResult,
    FetchMarketRefreshRequest,
    FetchMarketRefreshUseCase,
    FetchMarketTickerResult,
)
from src.application.use_case.refresh_daily_workspace_use_case import (
    DailyWorkspaceRefreshPlan,
    RefreshDailyWorkspaceRequest,
    RefreshDailyWorkspaceResult,
    RefreshDailyWorkspaceUseCase,
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
            # Emit the true fetch-market workflow contract:
            # on_ticker_complete(result: FetchMarketTickerResult, index, total).
            ticker_result = MagicMock(spec=FetchMarketTickerResult)
            ticker_result.ticker = "BBRI"
            on_ticker_complete(ticker_result, 1, 45)
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
    assert progress_events[1]["ticker"] == "BBRI"
    assert progress_events[1]["index"] == 1
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


def _non_empty_briefing() -> MagicMock:
    briefing = MagicMock(spec=DailyBriefingResponse)
    briefing.universe_count = 45
    briefing.regime = None
    briefing.opening_candidates = []
    briefing.market_wide_opening_observations = []
    briefing.accumulation_candidates = []
    briefing.daily_accumulation_candidates = [MagicMock()]
    briefing.setup_lens_impact = None
    return briefing


def test_refresh_generation_end_to_end_against_real_workflow_contracts() -> None:
    """Integration guard for the full Update path contract, no network/DB.

    Drives the real DailyController -> real RefreshDailyWorkspaceUseCase -> real
    FetchMarketRefreshUseCase (the production code that actually invokes
    ``on_ticker_complete``). Only the orthogonal briefing is stubbed. This wiring
    would have caught both Update-path crashes at once:

    * ``on_ticker_complete(result, index, total)`` arity — the controller's
      progress callback must accept the real 3-arg DTO shape production emits.
    * ``FetchMarketRefreshResponse.fail_count`` — the workspace use case reads the
      real field off a real response to build the failure warning.

    Hand-written stubs previously mirrored the buggy shapes, so the contract is
    exercised here through production code and real DTOs instead.
    """

    # A real refresh use case with in-memory fetch seams: one ticker errors so a
    # real non-zero fail_count flows through to the warning.
    def fake_fetch_candles(
        *,
        ticker,
        days,
        db_path,
        provider_name,
        refresh,
        short_history,
        effective_session=None,
    ):
        return "ERR: injected" if ticker == "FAIL" else "cached"

    def fake_fetch_broker(
        *,
        ticker,
        days,
        db_path,
        broker_provider,
        refresh,
        short_history,
        effective_session=None,
    ):
        return BrokerFetchResult(summaries="cached", flow="cached")

    real_refresh_use_case = FetchMarketRefreshUseCase(
        fetch_candles=fake_fetch_candles,
        fetch_broker=fake_fetch_broker,
        fetch_meta=lambda ticker, db_path: "cached",
        fetch_enrichment=lambda *a, **k: "skip",
        universe_loader=MagicMock(),
    )

    def recording_refresh_capability(request, on_start=None, on_ticker_complete=None):
        # Emit on_start with the real event DTO exactly like the command workflow.
        if on_start is not None:
            on_start(
                FetchMarketCommandStartEvent(
                    market_status_line=None,
                    market_is_open=False,
                    ticker_count=2,
                    days=request.days,
                    candles_provider="stockbit",
                    broker_provider_name="idx",
                    no_meta=True,
                    candles_only=False,
                    broker_only=False,
                    enrichment_available=False,
                )
            )
        # Production code emits on_ticker_complete with the real DTO/arity.
        response = real_refresh_use_case.execute(
            FetchMarketRefreshRequest(
                tickers=["BBCA", "FAIL"],
                universe=None,
                days=request.days,
                db_path=Path("unused.db"),
                candles_provider="stockbit",
                broker_provider=None,
                broker_provider_name="idx",
                refresh=False,
                candles_only=False,
                broker_only=False,
                no_meta=True,
                no_enrichment=True,
            ),
            on_ticker_complete=on_ticker_complete,
        )
        return FetchMarketCommandWorkflowResult(
            response=response,
            header=None,
            calendar_status="skip",
            expected_trading_day=date(2026, 7, 24),
            context_statuses=(),
        )

    briefing = _non_empty_briefing()
    briefing_use_case = MagicMock(spec=DailyBriefingUseCase)
    briefing_use_case.execute.return_value = briefing

    workspace_use_case = RefreshDailyWorkspaceUseCase(
        refresh_market_data_capability=recording_refresh_capability,
        daily_briefing_use_case=briefing_use_case,
    )

    controller = DailyController(
        load_daily=lambda: briefing,
        refresh_daily=workspace_use_case.execute,
    )

    generation = controller.begin()
    events: list = []
    progress: list = []
    controller.execute_refresh_generation(
        generation,
        RefreshDailyWorkspaceRequest(universe="lq45", days=10),
        dispatch=lambda callback, *args: callback(*args),
        listener=events.append,
        progress_callback=progress.append,
    )

    # on_ticker fired once per resolved ticker; benchmark IHSG is prepended.
    ticker_events = [e for e in progress if e["type"] == "ticker"]
    assert [e["ticker"] for e in ticker_events] == ["IHSG", "BBCA", "FAIL"]
    assert ticker_events[-1]["index"] == 3
    assert ticker_events[-1]["total"] == 3

    assert len(events) == 1
    assert events[0].status == ScreenStatus.READY
    # Real fail_count (1: the FAIL ticker) produced the summary warning.
    assert events[0].payload.warnings == ("1 ticker(s) failed during refresh.",)
