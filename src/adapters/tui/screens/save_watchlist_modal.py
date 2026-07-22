"""Modal dialog card for saving a named watchlist snapshot.

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class SaveWatchlistModal(ModalScreen[str | None]):
    """Modal dialog card to input watchlist snapshot name."""

    DEFAULT_CSS = """
    SaveWatchlistModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #save-card {
        width: 60;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #save-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #save-input {
        margin-bottom: 1;
    }

    #save-buttons {
        height: auto;
        align: right bottom;
        margin-top: 1;
    }

    #save-confirm-btn {
        margin-right: 2;
    }
    """

    def __init__(self, default_name: str = "my_shortlist") -> None:
        super().__init__()
        self._default_name = default_name

    def compose(self) -> ComposeResult:
        with Vertical(id="save-card"):
            yield Static("SAVE CANDIDATE SHORTLIST", id="save-title")
            yield Static("Enter a name for this watchlist snapshot:")
            yield Input(value=self._default_name, id="save-input")
            with Horizontal(id="save-buttons"):
                yield Button("Save Snapshot", variant="primary", id="save-confirm-btn")
                yield Button("Cancel", variant="error", id="save-cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-confirm-btn":
            inp = self.query_one("#save-input", Input).value.strip()
            self.dismiss(inp if inp else self._default_name)
        else:
            self.dismiss(None)
