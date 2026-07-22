"""Textual application and runtime entrypoint for the optional TUI adapter."""

from textual.app import App
from textual.binding import Binding

from src.adapters.tui.screens.daily import DailyShellScreen
from src.adapters.tui.screens.help import HelpScreen


class SahamTuiApp(App[None]):
    """Minimal offline shell shared by later read-only research screens."""

    TITLE = "AI Saham"
    SUB_TITLE = "Local research workspace"
    SCREENS = {
        "daily": DailyShellScreen,
        "help": HelpScreen,
    }
    BINDINGS = [Binding("q", "quit", "Quit")]
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
    """

    def on_mount(self) -> None:
        self.push_screen("daily")

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
