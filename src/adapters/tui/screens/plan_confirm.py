"""Deliberate Plan swing confirmation (OpenCode dialog language).

Enter confirms only inside this modal — never on the board list.

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class PlanConfirmModal(ModalScreen[bool | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "confirm", "Confirm", show=False, priority=True),
    ]

    def __init__(self, *, ticker: str, source: str, setup: str = "swing") -> None:
        super().__init__()
        self._ticker = ticker
        self._source = source
        self._setup = setup

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-card", classes="dialog-card narrow"):
            with Horizontal(id="confirm-head"):
                yield Static("Plan swing", id="confirm-title")
                yield Static("esc cancel", id="confirm-esc")
            body = (
                f"[bold #e8e8e8]Plan {self._ticker} · {self._setup}[/]\n"
                f"[dim]Deliberate action — Enter on a row only views.[/]\n\n"
                f"[dim]Ticker[/]   {self._ticker}\n"
                f"[dim]Profile[/]  {self._setup}\n"
                f"[dim]Source[/]   {self._source} · local\n"
                f"[dim]Horizon[/]  5–15 sessions\n\n"
                f"[#d4b06a]No broker order.[/] Plan records intent + setup\n"
                f"snapshot for audit. Discard later from Lab/CLI."
            )
            yield Static(body, id="confirm-body")
            yield Static("↵ confirm · esc cancel", id="confirm-foot")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)
