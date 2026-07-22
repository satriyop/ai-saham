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
            yield Static("q       Exit", classes="help-line")
            yield Static(
                "Phase 1 is navigation-only and performs no data access.",
                id="help-scope",
            )
        yield Footer()
