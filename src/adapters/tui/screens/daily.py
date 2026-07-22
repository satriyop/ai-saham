"""Minimal Daily route shell; Phase 2 will add the briefing capability."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class DailyShellScreen(Screen[None]):
    BINDINGS = [
        Binding("?", "app.show_help", "Help"),
        Binding("h", "app.show_help", "Help", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="daily-shell"):
            yield Static("Daily", id="daily-title")
            yield Static(
                "Offline research workspace ready. Daily data arrives in Phase 2.",
                id="daily-description",
            )
            yield Static("Press ? for help or q to exit.", id="daily-hint")
        yield Footer()
