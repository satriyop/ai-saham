"""Tests for Screen workspace controller, presenter, and screen.

Layer: Adapter
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from textual.widgets import Checkbox, Select, Static

from src.adapters.tui.composition import create_tui_app
from src.adapters.tui.controllers.screen_controller import (
    ScreenController,
    ScreenWorkspaceState,
)
from src.adapters.tui.screens.screen_workspace_screen import ScreenWorkspaceScreen

from .daily_fixtures import ready_response
from .research_fixtures import single_result
from src.adapters.tui.presenters.screen_presenter import (
    ScreenCandidateRowView,
    ScreenPresenter,
    ScreenViewModel,
)
from src.adapters.tui.state import ScreenStatus
from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.services.screen_accum_result_projector import (
    ScreenAccumMultiProjection,
    ScreenAccumSingleProjection,
)
from src.domain.value_objects.screen_snapshot import ScreenSnapshotEntry


def test_screen_presenter_formats_single_projection() -> None:
    cand = MagicMock(spec=AccumulationCandidate)
    cand.ticker = "BBRI"
    cand.accum_score = 80.0
    cand.consecutive_streak = 5
    cand.net_buy_ratio = 0.20
    cand.bci_label = "ACCUMULATION"
    cand.setup_phase = "coiled spring"
    cand.risk_status = "OPEN"
    cand.action = "ENTER"
    cand.signal_score = None  # real candidates use signal_assessment
    cand.signal_assessment = SimpleNamespace(
        assessment=SimpleNamespace(score=78, signal_authority_coverage=0.91)
    )
    cand.signal_authority_coverage = None
    cand.vwap_discount_pct = 9.5

    proj = MagicMock(spec=ScreenAccumSingleProjection)
    proj.candidates = [cand]

    presenter = ScreenPresenter()
    view = presenter.present_accumulation(proj, universe_label="lq45")

    assert isinstance(view, ScreenViewModel)
    assert len(view.candidate_rows) == 1
    row = view.candidate_rows[0]
    assert row.ticker == "BBRI"
    assert row.canonical_rank == 1
    assert row.accum_score == 80.0
    assert row.signal_score == 78  # unwrapped from signal_assessment
    assert row.signal_authority_coverage == 0.91
    assert row.action == "ENTER"
    assert row.vwap_discount_pct == 9.5
    assert row.vwap_depth_label == "deep"
    assert view.result_status == "ok"
    assert any(a.command == "saham view BBRI" for a in view.related_actions)
    assert any(a.command == "saham analyze swing BBRI" for a in view.related_actions)


def test_screen_presenter_empty_status_and_no_related_actions() -> None:
    proj = MagicMock(spec=ScreenAccumSingleProjection)
    proj.candidates = []

    view = ScreenPresenter().present_accumulation(proj)

    assert view.result_status == "empty"
    assert view.candidate_rows == ()
    assert view.related_actions == ()


def test_screen_presenter_multi_survives_null_canonical_candidate() -> None:
    """B2: canonical_candidate may be None when only non-canonical windows hit."""
    from datetime import date

    from src.application.services.screen_accum_result_projector import (
        MultiScreenAppliedFilters,
        ScreenAccumMultiProjection,
        ScreenAccumMultiRow,
    )
    from src.application.use_case.run_accumulation_screen_workflow_use_case import (
        RunAccumulationScreenWorkflowResult,
    )

    only_30 = SimpleNamespace(
        ticker="TLKM",
        accum_score=55.0,
        consecutive_streak=2,
        net_buy_ratio=0.4,
        bci_label=None,
        vwap_discount_pct=1.0,
        signal_assessment=None,
        risk_assessment=None,
        setup_phase=None,
        trade_setup=None,
    )
    multi_row = ScreenAccumMultiRow(
        ticker="TLKM",
        candidates_by_window={7: None, 30: only_30, 90: None},
        pattern="building",
        trend="UP",
        tracked_broker_flow=None,
        canonical_window=7,
        canonical_candidate=None,
        signal_score=None,
        signal_authority_coverage=None,
        risk_status="OPEN",
        setup_phase=None,
        data_status=None,
        next_action="WATCH",
    )
    multi = ScreenAccumMultiProjection(
        rows=[multi_row],
        applied_filters=MultiScreenAppliedFilters(False, 20, "vwap"),
        requested_windows=[7, 30, 90],
        resolved_windows=[7, 30, 90],
        raw_ticker_count=1,
        projected_row_count=1,
        screened_at=date(2026, 7, 22),
        canonical_window=7,
    )

    view = ScreenPresenter().present_accumulation(
        RunAccumulationScreenWorkflowResult(multi_projection=multi, multi_results={})
    )

    assert len(view.candidate_rows) == 1
    row = view.candidate_rows[0]
    assert row.ticker == "TLKM"
    assert row.accum_score == 55.0
    assert row.action == "WATCH"
    assert view.is_multi is True
    assert view.resolved_windows == (7, 30, 90)
    assert row.pattern == "building"
    assert dict(row.window_accum) == {7: None, 30: 55.0, 90: None}
    assert "30s:55" in (row.window_shape_label or "")
    assert "7s:—" in (row.window_shape_label or "")


def test_screen_multi_table_shows_window_columns_and_pattern() -> None:
    """Option A: multi layout exposes 7s/30s/90s Accum + Pattern (not single layout)."""
    from datetime import date

    from src.application.services.screen_accum_result_projector import (
        MultiScreenAppliedFilters,
        ScreenAccumMultiProjection,
        ScreenAccumMultiRow,
    )
    from src.application.use_case.run_accumulation_screen_workflow_use_case import (
        RunAccumulationScreenWorkflowResult,
    )

    c7 = SimpleNamespace(
        ticker="BBRI",
        accum_score=74.0,
        consecutive_streak=4,
        net_buy_ratio=0.6,
        bci_label="CLUSTER",
        vwap_discount_pct=5.0,
        signal_assessment=SimpleNamespace(
            assessment=SimpleNamespace(score=70, signal_authority_coverage=0.8)
        ),
        risk_assessment=SimpleNamespace(risk_level_name="OPEN"),
        setup_phase=None,
        trade_setup=SimpleNamespace(action=SimpleNamespace(value="WATCH")),
    )
    c30 = SimpleNamespace(
        ticker="BBRI",
        accum_score=68.0,
        consecutive_streak=3,
        net_buy_ratio=0.5,
        bci_label=None,
        vwap_discount_pct=4.0,
        signal_assessment=None,
        risk_assessment=None,
        setup_phase=None,
        trade_setup=None,
    )
    multi_row = ScreenAccumMultiRow(
        ticker="BBRI",
        candidates_by_window={7: c7, 30: c30, 90: None},
        pattern="building",
        trend="UP",
        tracked_broker_flow=None,
        canonical_window=7,
        canonical_candidate=c7,
        signal_score=70.0,
        signal_authority_coverage=0.8,
        risk_status="OPEN",
        setup_phase=None,
        data_status=None,
        next_action="WATCH",
    )
    multi = ScreenAccumMultiProjection(
        rows=[multi_row],
        applied_filters=MultiScreenAppliedFilters(False, 20, "vwap"),
        requested_windows=[7, 30, 90],
        resolved_windows=[7, 30, 90],
        raw_ticker_count=1,
        projected_row_count=1,
        screened_at=date(2026, 7, 22),
        canonical_window=7,
    )
    payload = RunAccumulationScreenWorkflowResult(
        multi_projection=multi, multi_results={}
    )

    controller = ScreenController(
        load_universe=lambda u: [],
        run_accumulation=lambda req: payload,
    )
    screen = ScreenWorkspaceScreen(controller, ScreenPresenter())

    async def scenario() -> None:
        async with _Host(screen).run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            # Force multi render path with known payload
            from src.adapters.tui.state import ScreenState, ScreenStatus

            screen._operation = "ACCUM"
            screen._render_state(
                ScreenState(
                    status=ScreenStatus.READY,
                    payload=payload,
                    generation=1,
                )
            )
            await pilot.pause(0.05)
            status = str(screen.query_one("#candidate-status", Static).content)
            assert "MULTI" in status
            assert "7/30/90" in status
            table = screen.query_one("#candidate-table")
            # columns: # Ticker Disc% 7s 30s 90s Pattern Signal Risk Action
            assert table.row_count == 1
            row = table.get_row_at(0)
            flat = " ".join(str(c) for c in row)
            assert "BBRI" in flat
            assert "74" in flat  # 7s Accum
            assert "68" in flat  # 30s Accum
            assert "—" in flat or "-" in flat  # missing 90s
            assert "building" in flat
            preview = str(screen.query_one("#preview-content", Static).content)
            assert "MULTI" in preview
            assert "7s:74" in preview
            assert "building" in preview
            assert "CLUSTER" in preview

    asyncio.run(scenario())


def test_screen_save_shortlist_refuses_multi_window() -> None:
    """B1: multi+save is forbidden (CLI parity), not a partial/crash path."""
    from src.application.use_case.run_accumulation_screen_workflow_use_case import (
        RunAccumulationScreenWorkflowRequest,
    )

    fake_save = MagicMock()
    controller = ScreenController(
        load_universe=lambda u: [],
        run_accumulation=MagicMock(),
        save_watchlist=fake_save,
    )
    screen = ScreenWorkspaceScreen(controller, ScreenPresenter())
    screen._last_request = RunAccumulationScreenWorkflowRequest(
        tickers=["BBCA"],
        universe_label="lq45",
        universe_name="lq45",
        window=7,
        min_streak=0,
        min_accum_score=None,
        min_signal_score=None,
        min_piotroski=0,
        strategy_name=None,
        include_strategy_overlay=False,
        multi=True,
        windows=[7, 30, 90],
        top=20,
        save_name=None,
        save_enabled=False,
    )
    screen._current_projection = single_result()

    assert screen._perform_save("should-not-save") is None
    fake_save.execute.assert_not_called()


def test_screen_controller_executes_screening_and_saves_snapshot() -> None:
    fake_run = MagicMock()
    fake_run.return_value = MagicMock(spec=ScreenAccumSingleProjection)

    fake_save = MagicMock()
    mock_save_res = MagicMock()
    mock_save_res.saved_count = 1
    mock_save_res.name = "test_list"
    fake_save.execute.return_value = mock_save_res

    controller = ScreenController(
        load_universe=lambda u: [],
        run_accumulation=fake_run,
        save_watchlist=fake_save,
    )

    generation = controller.begin()
    events = []

    req = MagicMock()
    controller.execute_accumulation_generation(
        generation,
        req,
        dispatch=lambda cb, *args: cb(*args),
        listener=events.append,
    )

    assert fake_run.called
    assert len(events) == 1
    assert events[0].status == ScreenStatus.READY

    save_res = controller.save_current_snapshot("test_list", [], "lq45", 7)
    assert save_res is not None
    assert save_res.name == "test_list"


# --------------------------------------------------------------------------- #
# Behavioral regression guards for the roadmap interaction contract:
#   "Selection, focus, sorting, and tab changes never start work."
# --------------------------------------------------------------------------- #


async def _wait_for_candidate_screen(pilot, app) -> None:
    for _ in range(50):
        await pilot.pause(0.01)
        if isinstance(app.screen, ScreenWorkspaceScreen):
            return
    raise AssertionError("Candidate screen did not open")


def _recording_app():
    requests: list = []

    def load_accumulation(request):
        requests.append(request)
        return single_result()

    app = create_tui_app(
        daily_loader=lambda: ready_response(),
        accumulation_loader=load_accumulation,
    )
    return app, requests


def test_passive_control_change_does_not_run_screen() -> None:
    async def scenario() -> None:
        app, requests = _recording_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("2")
            await _wait_for_candidate_screen(pilot, app)
            for _ in range(30):
                await pilot.pause(0.01)
                if requests:
                    break
            assert len(requests) == 1  # single run on open

            # Passive control changes must NOT trigger a screen run.
            app.screen.query_one("#squeeze-check", Checkbox).value = True
            app.screen.query_one("#vwap-check", Checkbox).value = True
            app.screen.query_one("#window-select", Select).value = "30"
            await pilot.pause(0.05)
            assert len(requests) == 1

    asyncio.run(scenario())


def test_tab_switch_prompts_for_explicit_run_and_does_not_run() -> None:
    async def scenario() -> None:
        app, requests = _recording_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("2")
            await _wait_for_candidate_screen(pilot, app)
            for _ in range(30):
                await pilot.pause(0.01)
                if requests:
                    break
            assert len(requests) == 1  # single accumulation run on open

            # Switching tabs must never start work — only prompt for explicit Run.
            app.screen.query_one("#tab-universe").press()
            await pilot.pause(0.05)
            msg = str(app.screen.query_one("#candidate-table-message", Static).content)
            assert "Run" in msg and "universe" in msg.lower()
            assert len(requests) == 1  # no accumulation run started

            app.screen.query_one("#tab-saved").press()
            await pilot.pause(0.05)
            msg = str(app.screen.query_one("#candidate-table-message", Static).content)
            assert "Run" in msg
            assert len(requests) == 1

    asyncio.run(scenario())


def test_explicit_run_button_and_multi_toggle_execute_typed_requests() -> None:
    async def scenario() -> None:
        app, requests = _recording_app()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("2")
            await _wait_for_candidate_screen(pilot, app)
            for _ in range(30):
                await pilot.pause(0.01)
                if requests:
                    break
            assert [r.multi for r in requests] == [False]

            app.screen.query_one("#run-btn").press()  # explicit Run
            await pilot.pause(0.05)
            assert len(requests) == 2

            await pilot.press("m")  # explicit multi-window toggle
            for _ in range(30):
                await pilot.pause(0.01)
                if len(requests) == 3:
                    break
            assert requests[-1].multi is True

    asyncio.run(scenario())


def test_datatable_selection_updates_preview_and_enter_opens_ticker() -> None:
    """Selectable list: highlight updates preview; open action uses selected row."""
    opened: list[str] = []

    class _OpenHost(App):
        def __init__(self, screen) -> None:
            super().__init__()
            self._screen = screen

        def on_mount(self) -> None:
            self.push_screen(self._screen)

        def action_open_ticker(self, ticker: str) -> None:
            opened.append(ticker)

    controller = ScreenController(
        load_universe=lambda u: [],
        run_accumulation=lambda req: single_result(),
    )
    screen = ScreenWorkspaceScreen(controller, ScreenPresenter())

    async def scenario() -> None:
        async with _OpenHost(screen).run_test(size=(120, 40)) as pilot:
            for _ in range(40):
                await pilot.pause(0.01)
                if screen._candidate_rows:
                    break
            assert len(screen._candidate_rows) == 2
            assert screen._candidate_rows[0].ticker == "BBRI"

            # Move selection to second row and open.
            screen.action_next_row()
            await pilot.pause(0.02)
            selected = str(screen.query_one("#candidate-selected", Static).content)
            assert "BBCA" in selected
            preview = str(screen.query_one("#preview-content", Static).content)
            assert "BBCA" in preview

            screen.action_open_selected_ticker()
            assert opened == ["BBCA"]

    asyncio.run(scenario())


def test_save_uses_actual_screened_universe_and_window_not_hardcoded() -> None:
    fake_save = MagicMock()
    fake_save.execute.return_value = MagicMock(saved_count=2, name="idx30_list")

    controller = ScreenController(
        load_universe=lambda u: [],
        run_accumulation=MagicMock(),
        save_watchlist=fake_save,
    )

    presenter = ScreenPresenter()
    screen = ScreenWorkspaceScreen(controller, presenter)

    cand = MagicMock(spec=AccumulationCandidate)
    cand.ticker = "BMRI"
    projection = MagicMock(spec=ScreenAccumSingleProjection)
    projection.candidates = [cand]
    screen._current_projection = projection

    from src.application.use_case.run_accumulation_screen_workflow_use_case import (
        RunAccumulationScreenWorkflowRequest,
    )

    screen._last_request = RunAccumulationScreenWorkflowRequest(
        tickers=[], universe_label="idx30", universe_name="idx30", window=30,
        min_streak=0, min_accum_score=None, min_signal_score=None,
        min_piotroski=0, strategy_name=None, include_strategy_overlay=False,
        multi=False, windows=[], top=50, save_name=None, save_enabled=False,
    )

    result = screen._perform_save("idx30_list")

    assert result is not None
    saved_request = fake_save.execute.call_args.args[0]
    assert saved_request.universe == "idx30"  # not the old hardcoded "lq45"
    assert saved_request.window_days == 30  # not the old hardcoded 7


# --------------------------------------------------------------------------- #
# Universe and Saved/Compare tab functional coverage (host-app pilot).
# --------------------------------------------------------------------------- #

from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

from textual.app import App  # noqa: E402

from src.application.use_case.compare_screen_snapshots_use_case import (  # noqa: E402
    ScreenCompareResult,
)
from src.application.use_case.compare_screen_watchlist_use_case import (  # noqa: E402
    CompareScreenWatchlistResult,
)
from src.application.use_case.list_screen_watchlists_use_case import (  # noqa: E402
    ListScreenWatchlistsResult,
    ScreenWatchlistSummary,
)
from src.application.use_case.view_universe_summary_use_case import (  # noqa: E402
    UniverseTickerRow,
    UniverseViewResult,
)


class _Host(App):
    def __init__(self, screen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def _universe_result() -> UniverseViewResult:
    return UniverseViewResult(
        universe_name="lq45",
        ticker_count=1,
        updated="2026-07-22",
        as_of_date=date(2026, 7, 22),
        rows=[
            UniverseTickerRow(
                ticker="BBRI", name="Bank BRI", sector="Financials",
                last_close=Decimal("4840"), change_pct=1.2, volume=1000000,
                foreign_net_value=Decimal("5000000"), foreign_flow_ratio=0.18,
                latest_date=date(2026, 7, 22),
            )
        ],
        missing_candles=0,
        missing_flow=0,
    )


def test_universe_tab_loads_view_on_explicit_run() -> None:
    universe_calls: list[str] = []

    def load_universe(name):
        universe_calls.append(name)
        return _universe_result()

    controller = ScreenController(
        load_universe=load_universe,
        run_accumulation=lambda req: single_result(),
    )
    screen = ScreenWorkspaceScreen(controller, ScreenPresenter())

    async def scenario() -> None:
        async with _Host(screen).run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            screen.query_one("#tab-universe").press()  # switch: no work
            await pilot.pause(0.05)
            assert universe_calls == []  # tab change started nothing
            await pilot.press("r")  # explicit run
            for _ in range(30):
                await pilot.pause(0.01)
                if universe_calls:
                    break
            assert universe_calls == ["lq45"]
            table = screen.query_one("#candidate-table")
            # DataTable row contents: ticker and formatted close.
            assert table.row_count == 1
            row = table.get_row_at(0)
            assert "BBRI" in row
            assert any("4,840" in str(cell) for cell in row)

    asyncio.run(scenario())


def test_saved_tab_lists_then_compares_selected_snapshot() -> None:
    from datetime import datetime

    list_uc = MagicMock()
    list_uc.execute.return_value = ListScreenWatchlistsResult(
        summaries=(
            ScreenWatchlistSummary(
                name="my_list", latest_saved_at=datetime(2026, 7, 21, 10, 0),
                universe="lq45", window_days=7, ticker_count=2,
            ),
        ),
    )

    compare_uc = MagicMock()
    compare_uc.execute.return_value = CompareScreenWatchlistResult(
        saved_summary=ScreenWatchlistSummary(
            name="my_list", latest_saved_at=datetime(2026, 7, 21, 10, 0),
            universe="lq45", window_days=7, ticker_count=2,
        ),
        fresh_projection=MagicMock(),
        comparison=ScreenCompareResult(
            snapshot_name="my_list", new_tickers=["BBNI"], dropped_tickers=["BMRI"],
            changed=[], snapshot_count=2, fresh_count=1,
        ),
    )

    controller = ScreenController(
        load_universe=lambda n: _universe_result(),
        run_accumulation=lambda req: single_result(),
        list_watchlists=list_uc,
        compare_watchlist=compare_uc,
    )
    screen = ScreenWorkspaceScreen(controller, ScreenPresenter())

    async def scenario() -> None:
        async with _Host(screen).run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            screen.query_one("#tab-saved").press()
            await pilot.pause(0.05)
            await pilot.press("r")  # explicit list
            for _ in range(30):
                await pilot.pause(0.01)
                if list_uc.execute.called:
                    break
            table = screen.query_one("#candidate-table")
            assert table.row_count == 1
            assert "my_list" in table.get_row_at(0)

            await pilot.press("c")  # explicit compare selected
            for _ in range(30):
                await pilot.pause(0.01)
                if compare_uc.execute.called:
                    break
            assert compare_uc.execute.called
            table = screen.query_one("#candidate-table")
            # Compare groups rendered as DataTable rows.
            flat = " ".join(
                " ".join(str(cell) for cell in table.get_row_at(i))
                for i in range(table.row_count)
            )
            assert "New" in flat and "BBNI" in flat
            assert "Dropped" in flat and "BMRI" in flat

    asyncio.run(scenario())
