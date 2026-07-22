"""Textual application and runtime entrypoint for the optional TUI adapter."""

from textual.app import App
from textual.binding import Binding

from src.adapters.tui.controllers.daily_controller import DailyController
from src.adapters.tui.presenters.daily_presenter import DailyPresenter
from src.adapters.tui.screens.daily_screen import DailyScreen
from src.adapters.tui.screens.help import HelpScreen


class SahamTuiApp(App[None]):
    """Minimal offline shell shared by later read-only research screens."""

    TITLE = "AI Saham"
    SUB_TITLE = "OFFLINE"
    SCREENS = {"help": HelpScreen}
    BINDINGS = [
        Binding("1", "show_today", "Today"),
        Binding("q", "quit", "Quit"),
    ]
    CSS = """
    Screen {
        background: $surface;
    }

    #daily-shell, #help-shell {
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
    ) -> None:
        super().__init__()
        self._daily_controller = daily_controller
        self._daily_presenter = daily_presenter

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
        self.set_route_context("Today")

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
