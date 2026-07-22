"""Textual application and runtime entrypoint for the optional TUI adapter."""

from textual.app import App
from textual.binding import Binding

from src.adapters.tui.controllers.accumulation_controller import AccumulationController
from src.adapters.tui.controllers.daily_controller import DailyController
from src.adapters.tui.controllers.research_health_controller import ResearchHealthController
from src.adapters.tui.controllers.ticker_research_controller import TickerResearchController
from src.adapters.tui.presenters.accumulation_presenter import AccumulationPresenter
from src.adapters.tui.presenters.daily_presenter import DailyPresenter
from src.adapters.tui.presenters.research_health_presenter import ResearchHealthPresenter
from src.adapters.tui.presenters.ticker_research_presenter import TickerResearchPresenter
from src.adapters.tui.screens.candidate_browser_screen import CandidateBrowserScreen
from src.adapters.tui.screens.daily_screen import DailyScreen
from src.adapters.tui.screens.help import HelpScreen
from src.adapters.tui.screens.research_health_screen import ResearchHealthScreen
from src.adapters.tui.screens.ticker_research_screen import TickerResearchScreen


class SahamTuiApp(App[None]):
    """Minimal offline shell shared by later read-only research screens."""

    TITLE = "AI Saham"
    SUB_TITLE = "OFFLINE"
    SCREENS = {"help": HelpScreen}
    BINDINGS = [
        Binding("1", "show_today", "Today"),
        Binding("2", "show_candidates", "Candidates"),
        Binding("3", "show_research", "Research"),
        Binding("q", "quit", "Quit"),
    ]
    CSS = """
    Screen {
        background: $surface;
    }

    #daily-shell, #candidate-shell, #ticker-shell, #research-health-shell, #help-shell {
        width: 100%;
        height: 1fr;
        padding: 2 4;
    }

    #daily-title, #help-title {
        width: 100%;
        text-style: bold;
        color: $accent;
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

    #candidate-workspace {
        layout: vertical;
    }

    CandidateBrowserScreen.wide #candidate-workspace {
        layout: horizontal;
    }

    #candidate-list {
        width: 2fr;
    }

    #candidate-preview {
        width: 100%;
        padding-left: 2;
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
    }

    .semantic-ready {
        color: $success;
    }

    .semantic-warning {
        color: $warning;
    }

    .semantic-error {
        color: $error;
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
    """

    def __init__(
        self,
        daily_controller: DailyController,
        daily_presenter: DailyPresenter,
        accumulation_controller: AccumulationController,
        accumulation_presenter: AccumulationPresenter,
        ticker_controller: TickerResearchController,
        ticker_presenter: TickerResearchPresenter,
        research_health_controller: ResearchHealthController,
        research_health_presenter: ResearchHealthPresenter,
    ) -> None:
        super().__init__()
        self._daily_controller = daily_controller
        self._daily_presenter = daily_presenter
        self._accumulation_controller = accumulation_controller
        self._accumulation_presenter = accumulation_presenter
        self._ticker_controller = ticker_controller
        self._ticker_presenter = ticker_presenter
        self._research_health_controller = research_health_controller
        self._research_health_presenter = research_health_presenter

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
        if isinstance(self.screen, TickerResearchScreen):
            self.pop_screen()
            self.call_after_refresh(self.action_show_today)
            return
        if isinstance(self.screen, CandidateBrowserScreen):
            self.set_route_context("Today")
            self.pop_screen()
            return
        if isinstance(self.screen, ResearchHealthScreen):
            self.set_route_context("Today")
            self.pop_screen()
            return
        self.set_route_context("Today")

    def action_show_candidates(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
            return
        if isinstance(self.screen, TickerResearchScreen):
            self.set_route_context("Candidates")
            self.pop_screen()
            return
        if isinstance(self.screen, ResearchHealthScreen):
            self.pop_screen()
            self.call_after_refresh(self.action_show_candidates)
            return
        if not isinstance(self.screen, CandidateBrowserScreen):
            self.push_screen(
                CandidateBrowserScreen(
                    self._accumulation_controller,
                    self._accumulation_presenter,
                )
            )
        self.set_route_context("Candidates")

    def action_show_research(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
            return
        if isinstance(self.screen, TickerResearchScreen):
            self.pop_screen()
            self.call_after_refresh(self.action_show_research)
            return
        if isinstance(self.screen, CandidateBrowserScreen):
            self.pop_screen()
            self.call_after_refresh(self.action_show_research)
            return
        if not isinstance(self.screen, ResearchHealthScreen):
            self.push_screen(
                ResearchHealthScreen(
                    self._research_health_controller,
                    self._research_health_presenter,
                )
            )
        self.set_route_context("Research")

    def action_open_ticker(self, ticker: str) -> None:
        self.push_screen(
            TickerResearchScreen(
                ticker,
                self._ticker_controller,
                self._ticker_presenter,
            )
        )

    def action_show_help(self) -> None:
        if not isinstance(self.screen, HelpScreen):
            self.push_screen("help")

    def action_close_help(self) -> None:
        if isinstance(self.screen, HelpScreen):
            self.pop_screen()


def run_tui() -> None:
    """Construct and run the optional TUI from its one composition root."""
    from src.adapters.tui.composition import create_tui_app

    create_tui_app().run()
