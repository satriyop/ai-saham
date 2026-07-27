"""Milestone C — C0 Ticker Decision Workbench contract and negative tests.

Covers: exact refresh-mode -> provider-flag mapping, cached-only offline safety,
selection/tab changes never starting work, canonical/setup/preview authority
separation, and offline global search.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.adapters.tui.composition import create_tui_app
from src.adapters.tui.presenters.ticker_workbench_presenter import (
    TickerWorkbenchPresenter,
)
from src.adapters.tui.research_capabilities import (
    ResearchExecution,
    SerializedResearchCapabilities,
    build_ticker_request,
)
from src.adapters.tui.screens.ticker_search_modal import TickerSearchModal
from src.adapters.tui.screens.ticker_workbench_screen import TickerWorkbenchScreen
from src.adapters.tui.ticker_refresh_mode import TickerRefreshMode
from src.infrastructure.config.app_config import AppConfig

from .daily_fixtures import ready_response
from .research_fixtures import single_result, ticker_response

# --------------------------------------------------------------------------
# Refresh-mode mapping — the heart of the C0 contract
# --------------------------------------------------------------------------


def test_refresh_mode_flags_map_exactly():
    assert TickerRefreshMode.CACHED_ONLY.flags == (False, False)
    assert TickerRefreshMode.UPDATE_IF_STALE.flags == (True, False)
    assert TickerRefreshMode.FORCE_UPDATE.flags == (True, True)
    # Only refresh modes may reach a provider.
    assert TickerRefreshMode.CACHED_ONLY.touches_provider is False
    assert TickerRefreshMode.UPDATE_IF_STALE.touches_provider is True
    assert TickerRefreshMode.FORCE_UPDATE.touches_provider is True


def test_build_ticker_request_maps_mode_and_setup_exactly():
    config = AppConfig()
    cached = build_ticker_request(config, Path("x.db"), 30, "BBRI")
    assert (cached.auto_refresh, cached.force_refresh) == (False, False)
    assert cached.setup_name is None

    forced = build_ticker_request(
        config,
        Path("x.db"),
        30,
        "BBRI",
        mode=TickerRefreshMode.FORCE_UPDATE,
        setup="foreign-bounce",
    )
    assert (forced.auto_refresh, forced.force_refresh) == (True, True)
    assert forced.setup_name == "foreign-bounce"


# --------------------------------------------------------------------------
# Provider strictness + setup routing at the loader seam
# --------------------------------------------------------------------------


class _RecordingWorkflow:
    def __init__(self, ticker: str = "BBRI") -> None:
        self.requests = []
        self._ticker = ticker

    def execute(self, request):
        self.requests.append(request)
        return ticker_response(ticker=request.ticker)


def _capabilities(workflows):
    execution = ResearchExecution(
        accumulation=None,  # type: ignore[arg-type]
        swing_workflows=workflows,
        config=AppConfig(),
        db_path=Path("x.db"),
        tickers=[],
        flow_window=30,
    )
    return SerializedResearchCapabilities(lambda: execution)


def test_cached_only_request_never_enables_refresh_and_routes_by_setup():
    no_setup = _RecordingWorkflow()
    foreign = _RecordingWorkflow()
    caps = _capabilities({None: no_setup, "foreign-bounce": foreign})

    caps.load_ticker("BBRI", TickerRefreshMode.CACHED_ONLY, None)
    assert no_setup.requests[0].auto_refresh is False
    assert no_setup.requests[0].force_refresh is False
    assert foreign.requests == []  # setup routing kept them apart


def test_update_mode_enables_refresh_flag_on_selected_setup_workflow():
    no_setup = _RecordingWorkflow()
    foreign = _RecordingWorkflow()
    caps = _capabilities({None: no_setup, "foreign-bounce": foreign})

    caps.load_ticker("BBRI", TickerRefreshMode.UPDATE_IF_STALE, "foreign-bounce")
    assert foreign.requests[0].auto_refresh is True
    assert foreign.requests[0].force_refresh is False
    assert foreign.requests[0].setup_name == "foreign-bounce"
    assert no_setup.requests == []


# --------------------------------------------------------------------------
# Authority separation in the presenter
# --------------------------------------------------------------------------


def test_unavailable_signal_has_no_action_and_no_blockers():
    view = TickerWorkbenchPresenter().present(ticker_response(available=False))
    assert view.decision.badge.text == "UNAVAILABLE"
    assert view.decision.badge.severity == "unavailable"
    assert view.decision.blockers == ()


def test_preview_is_isolated_from_canonical_decision():
    view = TickerWorkbenchPresenter().present(ticker_response(preview_action="PREVIEW_ONLY"))
    # The optional preview lives only in its own section, never the decision badge.
    assert ("action", "PREVIEW_ONLY") in view.preview
    assert view.decision.badge.text != "PREVIEW_ONLY"


# --------------------------------------------------------------------------
# Screen behavior: selection and tab changes never start work
# --------------------------------------------------------------------------


def test_selection_and_tab_changes_never_run_analysis():
    calls = []

    def load_ticker(ticker, mode=None, setup=None):
        calls.append((ticker, mode, setup))
        return ticker_response(ticker=ticker)

    async def scenario() -> None:
        app = create_tui_app(
            daily_loader=lambda: ready_response(),
            accumulation_loader=lambda request: single_result(),
            ticker_loader=load_ticker,
            search_tickers=lambda prefix: ("BBRI",),
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            app.action_open_ticker("BBRI")
            await pilot.pause()
            assert isinstance(app.screen, TickerWorkbenchScreen)

            # Change mode, change setup, switch every tab — none may run analysis.
            app.screen.query_one("#wb-mode").value = TickerRefreshMode.FORCE_UPDATE.name
            app.screen.query_one("#wb-setup").value = "foreign-bounce"
            await pilot.click("#wb-tab-setup")
            await pilot.click("#wb-tab-signal_risk")
            await pilot.click("#wb-tab-overview")
            await pilot.pause()
            assert calls == []

            # Only explicit Run works, and it carries the exact selected mode/setup.
            await pilot.press("r")
            for _ in range(50):
                await pilot.pause(0.01)
                if calls:
                    break
            assert calls == [("BBRI", TickerRefreshMode.FORCE_UPDATE, "foreign-bounce")]

    asyncio.run(scenario())


# --------------------------------------------------------------------------
# Global `/` search is offline and opens the same workbench
# --------------------------------------------------------------------------


def test_search_shows_full_universe_not_capped():
    # Regression: the search previously stacked a 50-item (use case) and 20-item
    # (modal) cap, hiding most of the cached universe. All matches must be shown.
    universe = tuple(f"BB{i:03d}" for i in range(60))

    async def scenario() -> None:
        app = create_tui_app(
            daily_loader=lambda: ready_response(),
            accumulation_loader=lambda request: single_result(),
            ticker_loader=lambda ticker, mode=None, setup=None: ticker_response(ticker=ticker),
            search_tickers=lambda prefix: universe,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("slash")
            await pilot.pause()
            assert isinstance(app.screen, TickerSearchModal)
            assert len(app.screen._matches) == 60  # not truncated to 20

    asyncio.run(scenario())


def test_global_search_is_offline_and_opens_workbench():
    search_calls = []
    ticker_calls = []

    def search(prefix):
        search_calls.append(prefix)
        return tuple(t for t in ("BBRI", "BBCA", "ANTM") if t.startswith(prefix.upper()))

    def load_ticker(ticker, mode=None, setup=None):
        ticker_calls.append(ticker)
        return ticker_response(ticker=ticker)

    async def scenario() -> None:
        app = create_tui_app(
            daily_loader=lambda: ready_response(),
            accumulation_loader=lambda request: single_result(),
            ticker_loader=load_ticker,
            search_tickers=search,
        )
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("slash")
            await pilot.pause()
            assert isinstance(app.screen, TickerSearchModal)

            await pilot.press("b", "b", "c")  # "BBC" -> BBCA
            await pilot.pause()
            assert app.screen._matches == ("BBCA",)

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, TickerWorkbenchScreen)
            # Search never queried a provider, and opening the workbench did not
            # run analysis (Run is explicit).
            assert search_calls  # offline catalog was consulted
            assert ticker_calls == []

    asyncio.run(scenario())
