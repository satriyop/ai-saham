"""Help modal — product locks and keys (ADR-051).

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

HELP_BODY = """[#9b8fb8]Product locks[/]
· Cockpit, not IDE — no scenario tabs
· Ctrl+P is navigation
· Enter = view ticker (never plan)
· Plan is deliberate (p + confirm)
· Pre-open and accum are equal
· Online only via explicit Fetch

[#9b8fb8]Keys[/]
  ctrl+p   commands
  ↑↓ j k   move rows
  enter    view focused ticker
  p        plan swing (confirm)
  r        refresh local board
  esc      back / cancel
  ctrl+b   toggle sidebar
  ?        this help
  q        quit

[#9b8fb8]Design[/]
  docs/design/tui-cockpit-opencode.md
  ADR-051 clean break
"""


class HelpModal(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("enter", "close", "Close", show=False),
        Binding("question_mark", "close", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-card", classes="dialog-card"):
            with Horizontal(id="help-head"):
                yield Static("Help", id="help-title")
                yield Static("esc", id="help-esc")
            yield Static(HELP_BODY, id="help-body")
            yield Static("↵ / esc close", id="help-foot")

    def action_close(self) -> None:
        self.dismiss(None)
