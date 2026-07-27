"""Explicit online fetch confirmation — never silent on open.

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class FetchConfirmModal(ModalScreen[bool | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "confirm", "Confirm", show=False, priority=True),
    ]

    def __init__(self, *, plan_text: str) -> None:
        super().__init__()
        self._plan_text = plan_text

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-card", classes="dialog-card narrow"):
            with Horizontal(id="confirm-head"):
                yield Static("Fetch market data", id="confirm-title")
                yield Static("esc cancel", id="confirm-esc")
            body = (
                "[bold #e8e8e8]Leave local-first · explicit online[/]\n\n"
                f"{self._plan_text}\n\n"
                "[#d4b06a]This is the only path that may hit the network.[/]\n"
                "Cockpit never fetches on open."
            )
            yield Static(body, id="confirm-body")
            yield Static("↵ fetch · esc cancel", id="confirm-foot")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)
