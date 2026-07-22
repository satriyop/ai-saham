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
            yield Static("1       Today", classes="help-line")
            yield Static("2       Candidates", classes="help-line")
            yield Static("? / h   Open this help", classes="help-line")
            yield Static("Esc / d Return to Daily", classes="help-line")
            yield Static("r       Reload by local recomputation", classes="help-line")
            yield Static("q       Exit", classes="help-line")
            yield Static(
                "Reload reads local cached inputs and never fetches provider data.",
                id="help-scope",
            )
            yield Static(
                "Canonical verdict drives decisions; NON-CANONICAL PREVIEW is separate context.",
                id="help-authority",
            )
        yield Footer()
