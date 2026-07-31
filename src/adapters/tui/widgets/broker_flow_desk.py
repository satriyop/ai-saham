"""Broker desk flow-by-day widget — structured density bars (hub ``f``).

Present-only. Mock density: date · net · lot · bar — not monospaced dump only.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.broker_desk_flow_model import DISPLAY_LIMIT, BrokerDeskFlowModel


def _bar(pct: int, *, width: int = 16) -> str:
    filled = max(0, min(width, round(pct * width / 100)))
    return "█" * filled + "░" * (width - filled)


class BrokerFlowDesk(Vertical):
    DEFAULT_CSS = """
    BrokerFlowDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }
    BrokerFlowDesk .fl-title { text-style: bold; color: #e8e8e8; }
    BrokerFlowDesk .fl-sub { color: #6b6b6b; }
    BrokerFlowDesk .fl-scope { color: #9b8fb8; margin-bottom: 1; height: auto; }
    BrokerFlowDesk .fl-panel {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 0 1 1 1;
        height: auto;
        margin-bottom: 1;
    }
    BrokerFlowDesk .fl-head-row {
        height: auto;
        border-bottom: solid #1c1c1c;
        color: #6b6b6b;
        text-style: bold;
    }
    BrokerFlowDesk .fl-row {
        height: auto;
        width: 100%;
        border-top: solid #1c1c1c;
    }
    BrokerFlowDesk .fl-date { width: 12; color: #a0a0a0; }
    BrokerFlowDesk .fl-net { width: 12; text-align: right; text-style: bold; }
    BrokerFlowDesk .fl-net.pos { color: #6fbf8a; }
    BrokerFlowDesk .fl-net.neg { color: #c97a72; }
    BrokerFlowDesk .fl-lot { width: 10; color: #6b6b6b; text-align: right; }
    BrokerFlowDesk .fl-n { width: 4; color: #6b6b6b; text-align: right; }
    BrokerFlowDesk .fl-bar { width: 1fr; color: #3a5a48; }
    BrokerFlowDesk .fl-bar.neg { color: #5a3a3a; }
    BrokerFlowDesk .fl-empty { color: #6b6b6b; height: auto; margin: 1 0; }
    BrokerFlowDesk .fl-hub {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #3a4252;
        padding: 0 1;
        height: auto;
        color: #9b8fb8;
        margin-top: 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="fl-title", classes="fl-title")
        yield Static("", id="fl-sub", classes="fl-sub")
        yield Static("", id="fl-scope", classes="fl-scope")
        with Vertical(classes="fl-panel", id="fl-panel"):
            with Horizontal(classes="fl-head-row", id="fl-head"):
                yield Static("Date", classes="fl-date")
                yield Static("Net", classes="fl-net")
                yield Static("Lot", classes="fl-lot")
                yield Static("#", classes="fl-n")
                yield Static("bar", classes="fl-bar")
            for i in range(DISPLAY_LIMIT):
                with Horizontal(classes="fl-row", id=f"fl-row-{i}"):
                    yield Static("", id=f"fl-date-{i}", classes="fl-date")
                    yield Static("", id=f"fl-net-{i}", classes="fl-net")
                    yield Static("", id=f"fl-lot-{i}", classes="fl-lot")
                    yield Static("", id=f"fl-n-{i}", classes="fl-n")
                    yield Static("", id=f"fl-bar-{i}", classes="fl-bar")
                # Compat scrape target
                yield Static("", id=f"fl-row-text-{i}", classes="fl-date")
        yield Static("", id="fl-empty", classes="fl-empty")
        yield Static("", id="fl-hub", classes="fl-hub")

    def on_mount(self) -> None:
        self.display = False
        for i in range(DISPLAY_LIMIT):
            try:
                self.query_one(f"#fl-row-text-{i}", Static).display = False
            except Exception:
                pass

    def paint(self, model: BrokerDeskFlowModel) -> None:
        self.query_one("#fl-title", Static).update(f"Flow by day · {model.broker_code}")
        self.query_one("#fl-sub", Static).update(f"{model.broker_name} · {model.type_label}")
        self.query_one("#fl-scope", Static).update(model.scope_note)

        for i in range(DISPLAY_LIMIT):
            row_el = self.query_one(f"#fl-row-{i}", Horizontal)
            if i < len(model.days):
                d = model.days[i]
                row_el.display = True
                self.query_one(f"#fl-date-{i}", Static).update(d.date_label)
                net = self.query_one(f"#fl-net-{i}", Static)
                net.remove_class("pos")
                net.remove_class("neg")
                if d.tone in {"pos", "neg"}:
                    net.add_class(d.tone)
                net.update(d.net_display)
                self.query_one(f"#fl-lot-{i}", Static).update(d.lot_display)
                self.query_one(f"#fl-n-{i}", Static).update(d.ticker_count)
                bar = self.query_one(f"#fl-bar-{i}", Static)
                bar.remove_class("neg")
                if d.tone == "neg":
                    bar.add_class("neg")
                bar.update(_bar(d.bar_pct))
                # keep monoline for scrapers/tests that look for fl-row content
                mirror = self.query_one(f"#fl-row-text-{i}", Static)
                mirror.update(
                    f"{d.date_label}  {d.net_display}  {d.lot_display}  "
                    f"{d.ticker_count}  {_bar(d.bar_pct)}"
                )
            else:
                row_el.display = False
                self.query_one(f"#fl-date-{i}", Static).update("")
                self.query_one(f"#fl-net-{i}", Static).update("")
                self.query_one(f"#fl-lot-{i}", Static).update("")
                self.query_one(f"#fl-n-{i}", Static).update("")
                self.query_one(f"#fl-bar-{i}", Static).update("")
                self.query_one(f"#fl-row-text-{i}", Static).update("")

        empty = self.query_one("#fl-empty", Static)
        if model.empty:
            empty.update(model.empty_reason or "—")
            empty.display = True
        else:
            empty.update("")
            empty.display = False
        self.query_one("#fl-hub", Static).update(model.hub_keys)
