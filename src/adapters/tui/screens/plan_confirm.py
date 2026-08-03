"""Deliberate Plan swing confirmation (OpenCode dialog language).

Enter confirms only inside this modal — never on the board list.
Shows the same desk facts as the board (Signal/Accum/Action/Why) so plan
does not feel like a different product.

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from src.adapters.tui.theme import OC


class PlanConfirmModal(ModalScreen[bool | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("enter", "confirm", "Confirm", show=False, priority=True),
    ]

    def __init__(
        self,
        *,
        ticker: str,
        source: str,
        setup: str = "swing",
        signal: str = "—",
        accum: str = "—",
        action: str = "—",
        gate: str = "—",
        why: str = "",
    ) -> None:
        super().__init__()
        self._ticker = ticker
        self._source = source
        self._setup = setup
        self._signal = signal
        self._accum = accum
        self._action = action
        self._gate = gate
        self._why = why

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-card", classes="dialog-card narrow"):
            with Horizontal(id="confirm-head"):
                yield Static("Plan swing", id="confirm-title")
                yield Static("esc cancel", id="confirm-esc")
            why_line = f"[{OC.brass}]Why {self._action}[/]  {self._why}\n" if self._why else ""
            body = (
                f"[bold {OC.text_bright}]Plan {self._ticker} · {self._setup}[/]\n"
                f"[dim]Deliberate — Enter on a row only views.[/]\n\n"
                f"[dim]Ticker[/]   {self._ticker}\n"
                f"[dim]Signal[/]   {self._signal}\n"
                f"[dim]Accum[/]    {self._accum}\n"
                f"[dim]Action[/]   {self._action}\n"
                f"[dim]Gate[/]     {self._gate}\n"
                f"[dim]Source[/]   {self._source} · local\n"
                f"{why_line}"
                f"\n[{OC.brass}]No broker order.[/] Records intent + setup snapshot\n"
                f"for audit only. Not a live order."
            )
            yield Static(body, id="confirm-body")
            yield Static("↵ confirm · esc cancel", id="confirm-foot")

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)
