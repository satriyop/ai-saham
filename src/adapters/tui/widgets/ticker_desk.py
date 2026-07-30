"""Harga-mast ticker desk widget (design: tui-ticker-desk.html).

Price is the landscape. Cache dashboard only — not Action.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.ticker_desk_model import TickerDeskModel


class TickerDesk(Vertical):
    """Visual ticker instrument mounted inside stage-scroll."""

    DEFAULT_CSS = """
    TickerDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #080b12;
    }

    TickerDesk .td-title {
        text-style: bold;
        color: #e8e8e8;
    }

    TickerDesk .td-sub {
        color: #5c6575;
        margin-bottom: 1;
    }

    TickerDesk .td-identity {
        background: #0d121c;
        border: solid #1c2430;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    TickerDesk .td-ticker-mark {
        text-style: bold;
        color: #f4f0e8;
    }

    TickerDesk .td-name {
        color: #c9c3b8;
    }

    TickerDesk .td-chips {
        color: #5c6575;
        height: auto;
    }

    TickerDesk .td-fresh {
        color: #5c6575;
        height: auto;
        margin-top: 0;
    }

    TickerDesk .td-mast {
        background: #121a28;
        border: solid #2a2430;
        border-left: solid #e8b86d;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    TickerDesk .td-mast-lab {
        color: #e8b86d;
        text-style: bold;
    }

    TickerDesk .td-price-row {
        height: auto;
        margin: 1 0;
    }

    TickerDesk .td-currency {
        width: auto;
        color: #5c6575;
        padding-right: 1;
    }

    TickerDesk .td-price {
        width: auto;
        text-style: bold;
        color: #faf6ee;
        padding-right: 2;
    }

    TickerDesk .td-chg {
        width: auto;
        text-style: bold;
        color: #8b92a0;
    }

    TickerDesk .td-chg.pos { color: #7ecfb8; }
    TickerDesk .td-chg.neg { color: #e87a6e; }

    TickerDesk .td-horizon {
        height: auto;
        margin-top: 1;
    }

    TickerDesk .td-hz {
        width: 1fr;
        height: auto;
        padding-right: 1;
    }

    TickerDesk .td-hz-k {
        color: #5c6575;
        text-style: bold;
    }

    TickerDesk .td-hz-v {
        color: #f0ebe3;
        text-style: bold;
    }

    TickerDesk .td-hz-v.pos { color: #7ecfb8; }
    TickerDesk .td-hz-v.neg { color: #e87a6e; }

    TickerDesk .td-ribbon {
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-metric {
        width: 1fr;
        background: #0d121c;
        border: solid #1c2430;
        border-left: solid #a89cc9;
        padding: 0 1;
        margin-right: 1;
        height: auto;
    }

    TickerDesk .td-metric-k {
        color: #5c6575;
        text-style: bold;
    }

    TickerDesk .td-metric-v {
        color: #f0ebe3;
        text-style: bold;
    }

    TickerDesk .td-authority {
        background: #0d121c;
        border: solid #1c2430;
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
        color: #8b92a0;
    }

    TickerDesk .td-depth-title {
        color: #5c6575;
        text-style: bold;
        margin-bottom: 0;
    }

    TickerDesk .td-body {
        color: #8b92a0;
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-footer {
        color: #5c6575;
        height: auto;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._model: TickerDeskModel | None = None

    def compose(self) -> ComposeResult:
        yield Static("", classes="td-title", id="td-title")
        yield Static("", classes="td-sub", id="td-sub")
        with Vertical(classes="td-identity", id="td-identity"):
            yield Static("—", classes="td-ticker-mark", id="td-mark")
            yield Static("", classes="td-name", id="td-name")
            yield Static("", classes="td-chips", id="td-chips")
            yield Static("", classes="td-fresh", id="td-fresh")
        with Vertical(classes="td-mast", id="td-mast"):
            yield Static("HARGA MAST · LAST LOCAL CLOSE", classes="td-mast-lab", id="td-mast-lab")
            with Horizontal(classes="td-price-row", id="td-price-row"):
                yield Static("Rp", classes="td-currency")
                yield Static("—", classes="td-price", id="td-price")
                yield Static("", classes="td-chg", id="td-chg")
            with Horizontal(classes="td-horizon", id="td-horizon"):
                for i in range(4):
                    with Vertical(classes="td-hz", id=f"td-hz-{i}"):
                        yield Static("", classes="td-hz-k", id=f"td-hz-k-{i}")
                        yield Static("", classes="td-hz-v", id=f"td-hz-v-{i}")
        with Horizontal(classes="td-ribbon", id="td-ribbon"):
            for i in range(6):
                with Vertical(classes="td-metric", id=f"td-metric-{i}"):
                    yield Static("", classes="td-metric-k", id=f"td-metric-k-{i}")
                    yield Static("", classes="td-metric-v", id=f"td-metric-v-{i}")
        yield Static("", classes="td-authority", id="td-authority")
        yield Static("DEPTH · CACHE PANELS", classes="td-depth-title", id="td-depth-title")
        yield Static("", classes="td-body", id="td-body")
        yield Static("", classes="td-footer", id="td-footer")

    def paint(self, model: TickerDeskModel) -> None:
        self._model = model
        self.query_one("#td-title", Static).update(f"View · ticker desk · {model.ticker}")
        self.query_one("#td-sub", Static).update(
            f"local cache · not judgment · as of {model.as_of}"
        )
        self.query_one("#td-mark", Static).update(model.ticker)
        self.query_one("#td-name", Static).update(model.name if model.name != "—" else "")
        chips = " · ".join(x for x in (model.board, model.sector) if x and x != "—")
        self.query_one("#td-chips", Static).update(chips or "—")
        fresh = "  ".join(model.freshness) if model.freshness else "freshness —"
        self.query_one("#td-fresh", Static).update(fresh)

        self.query_one("#td-price", Static).update(model.price or "—")
        chg = self.query_one("#td-chg", Static)
        for c in ("pos", "neg"):
            chg.remove_class(c)
        if model.change_1d:
            chg.add_class(model.change_tone if model.change_tone in {"pos", "neg"} else "pos")
            chg.update(model.change_1d)
        else:
            chg.update("")

        for i in range(4):
            if i < len(model.horizons):
                hz = model.horizons[i]
                self.query_one(f"#td-hz-k-{i}", Static).update(hz.label.upper())
                v = self.query_one(f"#td-hz-v-{i}", Static)
                for c in ("pos", "neg"):
                    v.remove_class(c)
                if hz.tone in {"pos", "neg"}:
                    v.add_class(hz.tone)
                v.update(hz.value)
            else:
                self.query_one(f"#td-hz-k-{i}", Static).update("")
                self.query_one(f"#td-hz-v-{i}", Static).update("")

        for i in range(6):
            if i < len(model.metrics):
                m = model.metrics[i]
                self.query_one(f"#td-metric-k-{i}", Static).update(m.label.upper())
                self.query_one(f"#td-metric-v-{i}", Static).update(m.value)
            else:
                self.query_one(f"#td-metric-k-{i}", Static).update("")
                self.query_one(f"#td-metric-v-{i}", Static).update("")

        self.query_one("#td-authority", Static).update(
            f"[#d4b06a]{model.authority}[/] · never sets ENTER/WATCH/AVOID"
        )
        body = model.body or "—"
        # Cap depth so mast remains the landscape; full dump still scrollable.
        if len(body) > 6000:
            body = body[:6000] + "\n… [dim]truncated[/]"
        self.query_one("#td-body", Static).update(body)
        self.query_one("#td-footer", Static).update(model.footer)
