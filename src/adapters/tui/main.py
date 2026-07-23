"""Textual application and runtime entrypoint for the optional TUI adapter."""

from textual.app import App
from textual.binding import Binding

from src.adapters.tui.controllers.accumulation_controller import AccumulationController
from src.adapters.tui.controllers.daily_controller import DailyController
from src.adapters.tui.controllers.discover_controller import DiscoverController
from src.adapters.tui.controllers.ticker_research_controller import TickerResearchController
from collections.abc import Callable

from src.adapters.tui.presenters.accumulation_presenter import AccumulationPresenter
from src.adapters.tui.presenters.daily_presenter import DailyPresenter
from src.adapters.tui.presenters.discover_presenter import DiscoverPresenter
from src.adapters.tui.presenters.ticker_workbench_presenter import TickerWorkbenchPresenter
from src.adapters.tui.screens.candidate_browser_screen import CandidateBrowserScreen
from src.adapters.tui.screens.daily_screen import DailyScreen
from src.adapters.tui.screens.help import HelpScreen
from src.adapters.tui.screens.ticker_search_modal import TickerSearchModal
from src.adapters.tui.screens.ticker_workbench_screen import TickerWorkbenchScreen


class SahamTuiApp(App[None]):
    """Minimal offline shell shared by later read-only research screens."""

    TITLE = "AI Saham"
    SUB_TITLE = "OFFLINE"
    SCREENS = {"help": HelpScreen}
    BINDINGS = [
        Binding("1", "show_today", "Today"),
        Binding("2", "show_candidates", "Candidates"),
        Binding("slash", "search_ticker", "Search"),
        Binding("q", "quit", "Quit"),
    ]
    CSS = """
    Screen {
        background: $surface;
    }

    #daily-shell, #candidate-shell, #ticker-shell, #help-shell {
        width: 100%;
        height: 1fr;
        padding: 1 2;
    }

    #daily-title, #help-title {
        width: 100%;
        text-style: bold;
        color: $accent;
        margin-bottom: 0;
    }

    #daily-action-bar {
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }

    #daily-status {
        width: 1fr;
        content-align: left middle;
    }

    #update-btn {
        margin-right: 1;
    }

    #reload-btn {
        margin-right: 1;
    }

    #daily-progress {
        width: 100%;
        margin-bottom: 1;
    }

    #daily-description, #help-scope {
        margin-bottom: 1;
    }

    .help-line {
        height: 1;
    }

    #daily-content {
        height: 1fr;
    }

    #candidate-workspace, #ticker-content {
        height: 1fr;
    }

    #discover-tab-bar {
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }

    .tab-btn {
        margin-right: 1;
        min-width: 16;
        background: $surface;
        color: $text;
        border: round $primary-muted;
    }

    .tab-btn:hover {
        background: $primary;
        color: $text-primary;
    }

    .active-tab {
        background: $accent;
        color: $surface;
        text-style: bold;
        border: round $accent;
    }

    #filter-toolbar {
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }

    #filter-toolbar Select {
        width: 20;
        margin-right: 1;
    }

    #filter-toolbar Checkbox {
        margin-right: 2;
    }

    #candidate-workspace {
        layout: vertical;
    }

    CandidateBrowserScreen.wide #candidate-workspace {
        layout: horizontal;
    }

    #candidate-list {
        width: 100%;
        border: round $primary;
        padding: 0 1;
        background: $surface;
    }

    #candidate-list:focus {
        border: round $accent;
    }

    #candidate-preview {
        width: 100%;
        border: round $secondary;
        padding: 0 1;
        background: $surface-darken-1;
    }

    CandidateBrowserScreen.wide #candidate-list {
        width: 2fr;
    }

    CandidateBrowserScreen.wide #candidate-preview {
        width: 1fr;
    }

    CandidateBrowserScreen.compact #candidate-preview {
        display: none;
    }

    #minimum-size-warning {
        display: none;
        color: $error;
    }

    Screen.too-small #minimum-size-warning {
        display: block;
    }

    .daily-section {
        height: auto;
        margin-bottom: 1;
        background: $surface;
        border: round $primary;
        padding: 0 1;
    }

    .daily-section:focus {
        border: round $accent;
    }

    .semantic-ready {
        color: $success;
        text-style: bold;
    }

    .semantic-warning {
        color: $warning;
        text-style: bold;
    }

    .semantic-error {
        color: $error;
        text-style: bold;
    }

    .semantic-unavailable {
        color: $text-muted;
    }

    .semantic-info {
        color: $accent;
    }

    .non-canonical-preview {
        color: $secondary;
    }

    #workbench-shell {
        width: 100%;
        height: 1fr;
        padding: 1 2;
    }

    #wb-header {
        width: 100%;
        text-style: bold;
        color: $accent;
    }

    #wb-verdict {
        width: 100%;
        text-style: bold;
    }

    #wb-blockers, #wb-status {
        width: 100%;
        color: $text-muted;
    }

    #wb-controls {
        height: 3;
        margin: 1 0;
        align: left middle;
    }

    #wb-controls Select {
        width: 24;
        margin-right: 1;
    }

    #wb-tab-bar {
        height: 3;
        margin-bottom: 1;
        align: left middle;
    }

    #wb-content {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
        background: $surface;
    }

    #wb-content:focus {
        border: round $accent;
    }

    TickerSearchModal {
        align: center middle;
    }

    #ticker-search-card {
        width: 64;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        background: $surface;
        border: thick $accent;
    }

    #ticker-search-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #ticker-search-results {
        height: auto;
        max-height: 16;
        margin-top: 1;
    }

    #ticker-search-status {
        color: $text-muted;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        daily_controller: DailyController,
        daily_presenter: DailyPresenter,
        accumulation_controller: AccumulationController | DiscoverController,
        accumulation_presenter: AccumulationPresenter | DiscoverPresenter,
        ticker_controller: TickerResearchController,
        ticker_presenter: TickerWorkbenchPresenter,
        *,
        search_tickers: Callable[[str], tuple[str, ...]],
    ) -> None:
        super().__init__()
        self._daily_controller = daily_controller
        self._daily_presenter = daily_presenter
        self._accumulation_controller = accumulation_controller
        self._accumulation_presenter = accumulation_presenter
        self._ticker_controller = ticker_controller
        self._ticker_presenter = ticker_presenter
        self._search_tickers = search_tickers

    def on_mount(self) -> None:
        self.set_route_context("Today")
        self.push_screen(DailyScreen(self._daily_controller, self._daily_presenter))

    def set_route_context(
        self,
        route: str,
        *,
        universe: str | None = None,
        as_of: str | None = None,
    ) -> None:
        self.title = f"AI Saham · {route}"
        details = ["OFFLINE"]
        if universe:
            details.append(universe.upper())
        if as_of:
            details.append(f"EOD {as_of}")
        self.sub_title = " · ".join(details)

    def action_show_today(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
            return
        if isinstance(self.screen, TickerWorkbenchScreen):
            self._cancel_active_screen_work()
            self.pop_screen()
            self.call_after_refresh(self.action_show_today)
            return
        if isinstance(self.screen, CandidateBrowserScreen):
            self._cancel_active_screen_work()
            self.set_route_context("Today")
            self.pop_screen()
            return
        self.set_route_context("Today")

    def action_show_candidates(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
            return
        if isinstance(self.screen, TickerWorkbenchScreen):
            self._cancel_active_screen_work()
            self.set_route_context("Candidates")
            self.pop_screen()
            return
        if not isinstance(self.screen, CandidateBrowserScreen):
            self._cancel_active_screen_work()
            self.push_screen(
                CandidateBrowserScreen(
                    self._accumulation_controller,
                    self._accumulation_presenter,
                )
            )
        self.set_route_context("Candidates")

    def action_open_ticker(self, ticker: str) -> None:
        self._cancel_active_screen_work()
        self.push_screen(
            TickerWorkbenchScreen(
                ticker,
                self._ticker_controller,
                self._ticker_presenter,
            )
        )

    def action_search_ticker(self) -> None:
        """Open the offline global ticker search. Selecting a ticker opens the
        same workbench used by the Discover drilldown. Opening search — and typing
        in it — never queries a provider."""
        if isinstance(self.screen, (HelpScreen, TickerSearchModal)):
            return

        def _on_dismiss(ticker: str | None) -> None:
            if ticker:
                self.action_open_ticker(ticker)

        self.push_screen(TickerSearchModal(self._search_tickers), _on_dismiss)

    def action_show_help(self) -> None:
        if not isinstance(self.screen, HelpScreen):
            self.push_screen("help")

    def action_close_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()

    def action_quit(self) -> None:
        self.workers.cancel_all()
        self.exit()

    def _cancel_active_screen_work(self) -> None:
        cancel = getattr(self.screen, "cancel_active_work", None)
        if cancel is not None:
            cancel()


def run_tui() -> None:
    """Construct and run the optional TUI from its one composition root."""
    from src.adapters.tui.composition import create_tui_app

    create_tui_app().run()
