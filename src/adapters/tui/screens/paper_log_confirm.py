"""Explicit paper notebook confirm from plan stage — no auto-log.

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class PaperLogConfirmModal(ModalScreen[bool | None]):
    """Confirm paper journal write (CLI parity: trade accum log --from-plan)."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "confirm", "Confirm", show=False, priority=True),
    ]

    def __init__(self, *, plan_text: str, ticker: str = "") -> None:
        super().__init__()
        self._plan_text = plan_text
        self._ticker = (ticker or "").upper()

    def compose(self) -> ComposeResult:
        title = f"Paper log · {self._ticker}" if self._ticker else "Paper log · notebook"
        with Vertical(id="confirm-card", classes="dialog-card narrow"):
            with Horizontal(id="confirm-head"):
                yield Static(title, id="confirm-title")
                yield Static("esc cancel", id="confirm-esc")
            body = (
                "[bold #e8e8e8]Log paper notebook entry[/]\n\n"
                f"{self._plan_text}\n\n"
                "[#d4b06a]Paper only · no broker order.[/]\n"
                "Same path as: saham trade accum log --from-plan"
            )
            yield Static(body, id="confirm-body")
            yield Static("↵ log paper · esc cancel", id="confirm-foot")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)
