"""Broker top-stocks dual-heat widget — latest session buy + sell.

Present-only. Design: cockpit hub ``t`` · mock ``stock-heat`` dual columns
(rank · ticker · heat bar · net · lot), not a monospaced dump.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.broker_desk_top_model import (
    DISPLAY_LIMIT,
    BrokerDeskTopModel,
    BrokerTopHeatRow,
)


def _bar_glyphs(pct: int, *, width: int = 14) -> str:
    filled = max(0, min(width, round(pct * width / 100)))
    return "█" * filled + "░" * (width - filled)


class BrokerTopDesk(Vertical):
    """Dual-side latest-session heat for desk hub ``t``."""

    DEFAULT_CSS = """
    BrokerTopDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }

    BrokerTopDesk .tp-title {
        text-style: bold;
        color: #e8e8e8;
    }

    BrokerTopDesk .tp-sub {
        color: #6b6b6b;
        margin-bottom: 0;
    }

    BrokerTopDesk .tp-scope {
        color: #9b8fb8;
        margin-bottom: 1;
        height: auto;
    }

    BrokerTopDesk .tp-cols {
        height: auto;
        margin-bottom: 1;
    }

    BrokerTopDesk .tp-col {
        width: 1fr;
        height: auto;
        background: #141414;
        border: solid #1c1c1c;
        padding: 0 1 1 1;
        margin-right: 1;
    }

    BrokerTopDesk .tp-col.buy {
        border-left: solid #6fbf8a;
    }

    BrokerTopDesk .tp-col.sell {
        border-left: solid #c97a72;
        margin-right: 0;
    }

    BrokerTopDesk .tp-col-title {
        color: #6fbf8a;
        text-style: bold;
        margin-bottom: 0;
        height: auto;
        border-bottom: solid #1c1c1c;
        padding-bottom: 0;
    }

    BrokerTopDesk .tp-col-title.sell {
        color: #c97a72;
    }

    BrokerTopDesk .tp-row {
        height: auto;
        width: 100%;
        padding: 0 0;
        border-top: solid #1c1c1c;
        color: #c8c8c8;
    }

    BrokerTopDesk .tp-rank {
        width: 3;
        color: #6b6b6b;
        text-style: bold;
    }

    BrokerTopDesk .tp-t {
        width: 7;
        color: #ececec;
        text-style: bold;
    }

    BrokerTopDesk .tp-bar {
        width: 1fr;
        color: #3a5a48;
        height: auto;
    }

    BrokerTopDesk .tp-bar.sell {
        color: #5a3a3a;
    }

    BrokerTopDesk .tp-n {
        width: 10;
        text-align: right;
        text-style: bold;
        color: #6fbf8a;
    }

    BrokerTopDesk .tp-n.sell {
        color: #c97a72;
    }

    BrokerTopDesk .tp-lot {
        width: 10;
        color: #6b6b6b;
        text-align: right;
    }

    BrokerTopDesk .tp-empty {
        color: #6b6b6b;
        height: auto;
        margin: 1 0;
    }

    BrokerTopDesk .tp-hub {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #3a4252;
        padding: 0 1;
        height: auto;
        color: #9b8fb8;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="tp-title", classes="tp-title")
        yield Static("", id="tp-sub", classes="tp-sub")
        yield Static("", id="tp-scope", classes="tp-scope")
        with Horizontal(classes="tp-cols", id="tp-cols"):
            with Vertical(classes="tp-col buy", id="tp-buy-col"):
                yield Static(
                    "TOP BUY · LATEST",
                    id="tp-buy-title",
                    classes="tp-col-title",
                )
                for i in range(DISPLAY_LIMIT):
                    with Horizontal(classes="tp-row", id=f"tp-buy-row-{i}"):
                        yield Static("", id=f"tp-buy-rank-{i}", classes="tp-rank")
                        # #tp-buy-{i} = ticker cell (tests + scrapers)
                        yield Static("", id=f"tp-buy-{i}", classes="tp-t")
                        yield Static("", id=f"tp-buy-bar-{i}", classes="tp-bar")
                        yield Static("", id=f"tp-buy-n-{i}", classes="tp-n")
                        yield Static("", id=f"tp-buy-lot-{i}", classes="tp-lot")
            with Vertical(classes="tp-col sell", id="tp-sell-col"):
                yield Static(
                    "TOP SELL · LATEST",
                    id="tp-sell-title",
                    classes="tp-col-title sell",
                )
                for i in range(DISPLAY_LIMIT):
                    with Horizontal(classes="tp-row", id=f"tp-sell-row-{i}"):
                        yield Static("", id=f"tp-sell-rank-{i}", classes="tp-rank")
                        yield Static("", id=f"tp-sell-{i}", classes="tp-t")
                        yield Static(
                            "",
                            id=f"tp-sell-bar-{i}",
                            classes="tp-bar sell",
                        )
                        yield Static(
                            "",
                            id=f"tp-sell-n-{i}",
                            classes="tp-n sell",
                        )
                        yield Static("", id=f"tp-sell-lot-{i}", classes="tp-lot")
        yield Static("", id="tp-empty", classes="tp-empty")
        yield Static("", id="tp-hub", classes="tp-hub")

    def on_mount(self) -> None:
        self.display = False

    def paint(self, model: BrokerDeskTopModel) -> None:
        self.query_one("#tp-title", Static).update(f"Buy / sell · {model.broker_code}")
        self.query_one("#tp-sub", Static).update(
            f"{model.broker_name} · {model.type_label} · {model.session_date} · latest session"
        )
        self.query_one("#tp-scope", Static).update(model.scope_note)
        self.query_one("#tp-buy-title", Static).update("Top buy · latest")
        self.query_one("#tp-sell-title", Static).update("Top sell · latest")

        self._paint_side(side="buy", rows=model.buys, empty_first=not model.buys)
        self._paint_side(side="sell", rows=model.sells, empty_first=not model.sells)

        empty = self.query_one("#tp-empty", Static)
        if model.empty:
            empty.update(model.empty_reason or "—")
            empty.display = True
        else:
            empty.update("")
            empty.display = False

        self.query_one("#tp-hub", Static).update(model.hub_keys)

    def _paint_side(
        self,
        *,
        side: str,
        rows: tuple[BrokerTopHeatRow, ...],
        empty_first: bool,
    ) -> None:
        for i in range(DISPLAY_LIMIT):
            row_el = self.query_one(f"#tp-{side}-row-{i}", Horizontal)
            rank_el = self.query_one(f"#tp-{side}-rank-{i}", Static)
            t_el = self.query_one(f"#tp-{side}-{i}", Static)
            bar_el = self.query_one(f"#tp-{side}-bar-{i}", Static)
            n_el = self.query_one(f"#tp-{side}-n-{i}", Static)
            lot_el = self.query_one(f"#tp-{side}-lot-{i}", Static)

            if i < len(rows):
                r = rows[i]
                row_el.display = True
                rank_el.update(str(i + 1))
                t_el.update(r.ticker)
                bar_el.update(_bar_glyphs(r.bar_pct))
                n_el.update(r.net_display)
                lot_el.update(r.lot_display)
            elif empty_first and i == 0:
                row_el.display = True
                rank_el.update("—")
                t_el.update("—")
                bar_el.update("")
                n_el.update("—")
                lot_el.update("")
            else:
                row_el.display = False
                rank_el.update("")
                t_el.update("")
                bar_el.update("")
                n_el.update("")
                lot_el.update("")
