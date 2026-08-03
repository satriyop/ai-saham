"""Explicit paper notebook confirm from plan stage — no auto-log.

Design: tui-paper-journal.html notebook tape confirm.

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

    DEFAULT_CSS = """
    PaperLogConfirmModal {
        align: center middle;
    }

    PaperLogConfirmModal #confirm-card {
        width: 72;
        max-width: 90%;
        height: auto;
        background: #141414;
        border: solid #1a1810;
        border-left: solid #c9a68a;
        padding: 1 2;
    }

    PaperLogConfirmModal #confirm-title {
        text-style: bold;
        color: #c9a68a;
    }

    PaperLogConfirmModal #confirm-esc {
        color: #555555;
        text-align: right;
        width: 1fr;
    }

    PaperLogConfirmModal #confirm-body {
        height: auto;
        margin: 1 0;
        color: #d8d8d8;
    }

    PaperLogConfirmModal #confirm-foot {
        color: #555555;
        height: auto;
    }
    """

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
            # plan_text is already notebook-formatted by paper_log_display
            yield Static(self._plan_text, id="confirm-body")
            yield Static("↵ log paper · esc cancel · no broker order", id="confirm-foot")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)
