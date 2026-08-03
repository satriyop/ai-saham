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
from src.adapters.tui.theme import OC, bake_css


def _bar_glyphs(pct: int, *, width: int = 14) -> str:
    """Glyph track only (0–100 of-max). Pair with a ``%`` label — never alone."""
    p = max(0, min(100, int(pct or 0)))
    filled = max(0, min(width, round(p * width / 100)))
    return "█" * filled + "░" * (width - filled)


def _pct_label(pct: int) -> str:
    return f"{max(0, min(100, int(pct or 0)))}%"


def format_top_bar_cell(pct: int, *, width: int = 14, sell: bool = False) -> str:
    """Bar + mute ``%`` — mint buy / coral sell (bible scalar bar)."""
    p = max(0, min(100, int(pct or 0)))
    filled = max(0, min(width, round(p * width / 100)))
    tone = OC.coral if sell else OC.mint
    filled_s = "█" * filled
    rest_s = "░" * (width - filled)
    if filled <= 0:
        return f"[{OC.scalar_track}]{rest_s}[/] [{OC.text_mute}]{_pct_label(p)}[/]"
    return f"[{tone}]{filled_s}[/][{OC.scalar_track}]{rest_s}[/] [{OC.text_mute}]{_pct_label(p)}[/]"


class BrokerTopDesk(Vertical):
    """Dual-side latest-session heat for desk hub ``t``."""

    DEFAULT_CSS = bake_css("""
    BrokerTopDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: $oc_bg;
    }

    BrokerTopDesk .tp-title {
        text-style: bold;
        color: $oc_text_bright;
    }

    BrokerTopDesk .tp-sub {
        color: $oc_dim;
        margin-bottom: 0;
    }

    BrokerTopDesk .tp-scope {
        color: $oc_purple;
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
        background: $oc_bg_elevated;
        border: solid $oc_border;
        padding: 0 1 1 1;
        margin-right: 1;
    }

    BrokerTopDesk .tp-col.buy {
        border-left: solid $oc_mint;
    }

    BrokerTopDesk .tp-col.sell {
        border-left: solid $oc_coral;
        margin-right: 0;
    }

    BrokerTopDesk .tp-col-title {
        color: $oc_mint;
        text-style: bold;
        margin-bottom: 0;
        height: auto;
        border-bottom: solid $oc_border;
        padding-bottom: 0;
    }

    BrokerTopDesk .tp-col-title.sell {
        color: $oc_coral;
    }

    BrokerTopDesk .tp-row {
        height: auto;
        width: 100%;
        padding: 0 0;
        border-top: solid $oc_border;
        color: $oc_text;
    }

    BrokerTopDesk .tp-rank {
        width: 3;
        color: $oc_dim;
        text-style: bold;
    }

    BrokerTopDesk .tp-t {
        width: 7;
        color: $oc_text_bright;
        text-style: bold;
    }

    BrokerTopDesk .tp-bar {
        width: 1fr;
        color: $oc_mint;
        height: auto;
    }

    BrokerTopDesk .tp-bar.sell {
        color: $oc_coral;
    }

    BrokerTopDesk .tp-n {
        width: 10;
        text-align: right;
        text-style: bold;
        color: $oc_mint;
    }

    BrokerTopDesk .tp-n.sell {
        color: $oc_coral;
    }

    BrokerTopDesk .tp-lot {
        width: 10;
        color: $oc_dim;
        text-align: right;
    }

    BrokerTopDesk .tp-empty {
        color: $oc_dim;
        height: auto;
        margin: 1 0;
    }

    BrokerTopDesk .tp-hub {
        background: $oc_bg_elevated;
        border: solid $oc_border;
        border-left: solid $oc_hairline_strong;
        padding: 0 1;
        height: auto;
        color: $oc_purple;
    }
    """)

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
                bar_el.update(format_top_bar_cell(r.bar_pct, sell=(side == "sell")))
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
