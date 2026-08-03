"""Broker desk history widget — structured per-ticker daily rows (hub ``h``).

Present-only. Density UI: date · ticker · net · lot.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.broker_desk_history_model import (
    DISPLAY_LIMIT,
    BrokerDeskHistoryModel,
)
from src.adapters.tui.theme import bake_css


class BrokerHistoryDesk(Vertical):
    DEFAULT_CSS = bake_css("""
    BrokerHistoryDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: $oc_bg;
    }
    BrokerHistoryDesk .hi-title { text-style: bold; color: $oc_text_bright; }
    BrokerHistoryDesk .hi-sub { color: $oc_dim; }
    BrokerHistoryDesk .hi-scope { color: $oc_purple; margin-bottom: 1; height: auto; }
    BrokerHistoryDesk .hi-panel {
        background: $oc_bg_elevated;
        border: solid $oc_border;
        border-left: solid $oc_peach;
        padding: 0 1 1 1;
        height: auto;
        margin-bottom: 1;
    }
    BrokerHistoryDesk .hi-head-row {
        height: auto;
        border-bottom: solid $oc_border;
        color: $oc_dim;
        text-style: bold;
    }
    BrokerHistoryDesk .hi-row {
        height: auto;
        width: 100%;
        border-top: solid $oc_border;
    }
    BrokerHistoryDesk .hi-date { width: 12; color: $oc_text_dim; }
    BrokerHistoryDesk .hi-t { width: 8; color: $oc_text_bright; text-style: bold; }
    BrokerHistoryDesk .hi-net { width: 12; text-align: right; text-style: bold; }
    BrokerHistoryDesk .hi-net.pos { color: $oc_mint; }
    BrokerHistoryDesk .hi-net.neg { color: $oc_coral; }
    BrokerHistoryDesk .hi-lot { width: 10; color: $oc_dim; text-align: right; }
    BrokerHistoryDesk .hi-empty { color: $oc_dim; height: auto; margin: 1 0; }
    BrokerHistoryDesk .hi-trunc { color: $oc_dim; height: auto; }
    BrokerHistoryDesk .hi-hub {
        background: $oc_bg_elevated;
        border: solid $oc_border;
        border-left: solid $oc_hairline_strong;
        padding: 0 1;
        height: auto;
        color: $oc_purple;
        margin-top: 0;
    }
    """)

    def compose(self) -> ComposeResult:
        yield Static("", id="hi-title", classes="hi-title")
        yield Static("", id="hi-sub", classes="hi-sub")
        yield Static("", id="hi-scope", classes="hi-scope")
        with Vertical(classes="hi-panel", id="hi-panel"):
            with Horizontal(classes="hi-head-row", id="hi-head"):
                yield Static("Date", classes="hi-date")
                yield Static("Ticker", classes="hi-t")
                yield Static("Net", classes="hi-net")
                yield Static("Lot", classes="hi-lot")
            for i in range(DISPLAY_LIMIT):
                with Horizontal(classes="hi-row", id=f"hi-row-{i}"):
                    yield Static("", id=f"hi-date-{i}", classes="hi-date")
                    yield Static("", id=f"hi-t-{i}", classes="hi-t")
                    yield Static("", id=f"hi-net-{i}", classes="hi-net")
                    yield Static("", id=f"hi-lot-{i}", classes="hi-lot")
        yield Static("", id="hi-trunc", classes="hi-trunc")
        yield Static("", id="hi-empty", classes="hi-empty")
        yield Static("", id="hi-hub", classes="hi-hub")

    def on_mount(self) -> None:
        self.display = False

    def paint(self, model: BrokerDeskHistoryModel) -> None:
        pin = f" · pin {model.pinned_ticker}" if model.pinned_ticker else ""
        self.query_one("#hi-title", Static).update(f"History · {model.broker_code}{pin}")
        self.query_one("#hi-sub", Static).update(f"{model.broker_name} · {model.type_label}")
        self.query_one("#hi-scope", Static).update(model.scope_note)

        for i in range(DISPLAY_LIMIT):
            row_el = self.query_one(f"#hi-row-{i}", Horizontal)
            if i < len(model.rows):
                r = model.rows[i]
                row_el.display = True
                self.query_one(f"#hi-date-{i}", Static).update(r.date_label)
                self.query_one(f"#hi-t-{i}", Static).update(r.ticker)
                net = self.query_one(f"#hi-net-{i}", Static)
                net.remove_class("pos")
                net.remove_class("neg")
                if r.tone in {"pos", "neg"}:
                    net.add_class(r.tone)
                net.update(r.net_display)
                self.query_one(f"#hi-lot-{i}", Static).update(r.lot_display)
            else:
                row_el.display = False
                self.query_one(f"#hi-date-{i}", Static).update("")
                self.query_one(f"#hi-t-{i}", Static).update("")
                self.query_one(f"#hi-net-{i}", Static).update("")
                self.query_one(f"#hi-lot-{i}", Static).update("")

        trunc = self.query_one("#hi-trunc", Static)
        if model.truncated:
            trunc.update(f"… truncated {model.truncated} more rows")
            trunc.display = True
        else:
            trunc.update("")
            trunc.display = False

        empty = self.query_one("#hi-empty", Static)
        if model.empty:
            empty.update(model.empty_reason or "—")
            empty.display = True
        else:
            empty.update("")
            empty.display = False
        self.query_one("#hi-hub", Static).update(model.hub_keys)
