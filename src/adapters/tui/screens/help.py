"""Help modal — product locks and keys (ADR-051).

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

HELP_BODY = """[#9b8fb8]What this app does[/]
· Opens on [bold]Screen · accumulation[/] from local SQLite
· Pre-open reads cached IEV snapshots (fetch iev)
· Enter = [bold]Judge[/] focused accum row (ADR-054 · present-only)
· j on Judge = re-judge single ticker (local screen · not full board r)
· Snapshot board may open limited judge until j or live refresh
· p = plan structure desk (SL/TP/lots · inherits Action · no order)
· l on Plan = paper notebook log (confirm · trade accum log --from-plan)
· Judge shows phase sequence from setup phase ledger (ADR-058 · read-only)
· Fetch = explicit online (never on open)

[#9b8fb8]Keys[/]
  ctrl+p   commands
  ↑↓ j k   move rows (j = re-judge only on Judge stage)
  enter    judge (accum) / inspect (pre-open) / desk home
  s a      screen accumulation
  s p      screen pre-open
  v t      view ticker (CLI dashboard · needs focus)
  v b      view broker list
  p        plan structure (focused ticker)
  l        paper log (on plan stage · confirm first)
  r        refresh local board
  b        stock→desks (on view ticker only)
  t/f/h/v  desk hub (on broker show · v = top stock)
  esc      back / cancel · cancel chord prefix
  ctrl+b   toggle sidebar
  ?        this help
  q        quit

[#9b8fb8]Same engine as CLI[/]
  saham screen accum · screen pre-open · plan swing
  saham view ticker show · view broker …
  Lab backtests stay CLI for now (palette shows hint)
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
