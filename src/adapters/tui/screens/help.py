"""Keyboard help route for the minimal TUI shell."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class HelpScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "app.close_help", "Back"),
        Binding("d", "app.close_help", "Daily", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="help-shell"):
            yield Static("Help", id="help-title")
            yield Static("? / h   Open this help", classes="help-line")
            yield Static("Esc / d Return to Daily", classes="help-line")
            yield Static("r       Reload by local recomputation", classes="help-line")
            yield Static("q       Exit", classes="help-line")
            yield Static(
                "Reload reads local cached inputs. It never fetches provider data.",
                id="help-scope",
            )
        yield Footer()
