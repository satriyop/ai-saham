"""Paper notebook desk — session tape (design paper notebook stage).

Write remains confirm-gated from plan ``l``. This stage is browse of tape.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from src.adapters.tui.paper_desk_model import PaperDeskModel

_MAX_ROWS = 12


class PaperDesk(Vertical):
    DEFAULT_CSS = """
    PaperDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }
    PaperDesk .pp-title { text-style: bold; color: #e8e8e8; }
    PaperDesk .pp-sub { color: #6b6b6b; margin-bottom: 1; height: auto; }
    PaperDesk .pp-tape {
        background: #141414;
        border: solid #1c1c1c;
        padding: 1 1;
        height: auto;
        margin-bottom: 1;
    }
    PaperDesk .pp-row {
        height: auto;
        border-top: solid #1c1c1c;
        padding: 0 0;
        color: #c8c8c8;
    }
    PaperDesk .pp-row.ok { border-left: solid #6fbf8a; padding-left: 1; }
    PaperDesk .pp-row.refuse { border-left: solid #c97a72; padding-left: 1; }
    PaperDesk .pp-row.fail { border-left: solid #d4b06a; padding-left: 1; }
    PaperDesk .pp-empty { color: #6b6b6b; height: auto; margin: 1 0; }
    PaperDesk .pp-footer { color: #555555; height: auto; }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="pp-title", classes="pp-title")
        yield Static("", id="pp-sub", classes="pp-sub")
        with Vertical(classes="pp-tape", id="pp-tape"):
            for i in range(_MAX_ROWS):
                yield Static("", id=f"pp-row-{i}", classes="pp-row")
        yield Static("", id="pp-empty", classes="pp-empty")
        yield Static("", id="pp-footer", classes="pp-footer")

    def on_mount(self) -> None:
        self.display = False

    def paint(self, model: PaperDeskModel) -> None:
        self.query_one("#pp-title", Static).update(model.title)
        self.query_one("#pp-sub", Static).update(model.subtitle)
        for i in range(_MAX_ROWS):
            slot = self.query_one(f"#pp-row-{i}", Static)
            slot.remove_class("ok")
            slot.remove_class("refuse")
            slot.remove_class("fail")
            if i < len(model.rows):
                r = model.rows[i]
                slot.add_class(r.kind if r.kind in {"ok", "refuse", "fail"} else "fail")
                slot.update(f"[bold #e8e8e8]{r.headline}[/]\n[#6b6b6b]{r.sub}[/]")
                slot.display = True
            else:
                slot.update("")
                slot.display = False
        empty = self.query_one("#pp-empty", Static)
        if model.empty:
            empty.update(model.empty_reason)
            empty.display = True
        else:
            empty.update("")
            empty.display = False
        self.query_one("#pp-footer", Static).update(model.footer)
