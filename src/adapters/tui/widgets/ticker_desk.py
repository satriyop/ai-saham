"""Harga-mast ticker desk — design: docs/design/tui-ticker-desk.html.

Adopt: price is landscape · brass tape · horizon · ribbon · pulse trio ·
earnings · secondary kv. Reject: CLI dump as primary stage.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.ticker_desk_model import TickerDeskModel, bar_glyphs


class TickerDesk(Vertical):
    """Visual ticker instrument — night-ink Harga Mast."""

    DEFAULT_CSS = """
    TickerDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #080b12;
    }

    TickerDesk .td-crumb {
        color: #5c6575;
        margin-bottom: 1;
        height: auto;
    }

    /* Identity */
    TickerDesk .td-identity {
        height: auto;
        margin-bottom: 1;
        padding: 0 0 1 0;
        border-bottom: solid #1c2430;
    }

    TickerDesk .td-mark {
        text-style: bold;
        color: #f2eee6;
        width: auto;
        padding-right: 2;
    }

    TickerDesk .td-id-sub {
        width: 1fr;
        height: auto;
        color: #c9c3b8;
    }

    TickerDesk .td-fresh-col {
        width: auto;
        height: auto;
        color: #5c6575;
        text-align: right;
    }

    /* Mast */
    TickerDesk .td-mast {
        background: #121a28;
        border: solid #1c2430;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    TickerDesk .td-mast-left {
        width: 3fr;
        height: auto;
        padding-right: 2;
    }

    TickerDesk .td-mast-lab {
        color: #e8b86d;
        text-style: bold;
    }

    TickerDesk .td-price-row {
        height: auto;
        margin: 1 0 0 0;
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
        background: #182233;
        padding: 0 1;
    }

    TickerDesk .td-chg.pos {
        color: #7ecfb8;
        background: #14241c;
    }

    TickerDesk .td-chg.neg {
        color: #e87a6e;
        background: #241414;
    }

    TickerDesk .td-tape {
        color: #3a4252;
        height: auto;
        margin-top: 0;
    }

    TickerDesk .td-mast-right {
        width: 2fr;
        height: auto;
    }

    TickerDesk .td-hz-line {
        height: auto;
        color: #8b92a0;
    }

    /* Ribbon */
    TickerDesk .td-ribbon {
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-metric {
        width: 1fr;
        background: #0d121c;
        border: solid #1c2430;
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

    TickerDesk .td-metric-u {
        color: #3a4252;
    }

    /* Pulse trio */
    TickerDesk .td-trio {
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-pulse {
        width: 1fr;
        background: #0d121c;
        border: solid #1c2430;
        border-left: solid #8eb4d8;
        padding: 1 1;
        margin-right: 1;
        height: auto;
        color: #8b92a0;
    }

    TickerDesk .td-pulse.tone-pos { border-left: solid #7ecfb8; }
    TickerDesk .td-pulse.tone-neg { border-left: solid #e87a6e; }
    TickerDesk .td-pulse.tone-neutral { border-left: solid #a89cc9; }

    TickerDesk .td-pulse-title {
        color: #5c6575;
        text-style: bold;
    }

    TickerDesk .td-pulse-head {
        color: #f0ebe3;
        text-style: bold;
        height: auto;
    }

    TickerDesk .td-pulse-head.pos { color: #7ecfb8; }
    TickerDesk .td-pulse-head.neg { color: #e87a6e; }

    TickerDesk .td-pulse-sub {
        color: #5c6575;
        height: auto;
    }

    TickerDesk .td-pulse-body {
        color: #8b92a0;
        height: auto;
        margin-top: 0;
    }

    /* Earnings */
    TickerDesk .td-section {
        background: #0d121c;
        border: solid #1c2430;
        padding: 1 1;
        margin-bottom: 1;
        height: auto;
    }

    TickerDesk .td-sec-head {
        color: #5c6575;
        text-style: bold;
        height: auto;
    }

    TickerDesk .td-earn {
        color: #8b92a0;
        height: auto;
    }

    TickerDesk .td-sec-body {
        color: #8b92a0;
        height: auto;
    }

    TickerDesk .td-footer {
        color: #5c6575;
        height: auto;
        border-top: solid #1c2430;
        padding-top: 1;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._model: TickerDeskModel | None = None

    def compose(self) -> ComposeResult:
        yield Static("", classes="td-crumb", id="td-crumb")

        with Horizontal(classes="td-identity", id="td-identity"):
            yield Static("—", classes="td-mark", id="td-mark")
            with Vertical(classes="td-id-sub", id="td-id-sub"):
                yield Static("", id="td-name")
                yield Static("", id="td-chips")
            with Vertical(classes="td-fresh-col", id="td-fresh-col"):
                yield Static("", id="td-asof")
                yield Static("", id="td-fresh")

        with Horizontal(classes="td-mast", id="td-mast"):
            with Vertical(classes="td-mast-left", id="td-mast-left"):
                yield Static("LAST · LOCAL CLOSE", classes="td-mast-lab", id="td-mast-lab")
                with Horizontal(classes="td-price-row"):
                    yield Static("Rp", classes="td-currency")
                    yield Static("—", classes="td-price", id="td-price")
                    yield Static("", classes="td-chg", id="td-chg")
                yield Static("", classes="td-tape", id="td-tape")
            with Vertical(classes="td-mast-right", id="td-mast-right"):
                for i in range(4):
                    yield Static("", classes="td-hz-line", id=f"td-hz-{i}")

        with Horizontal(classes="td-ribbon", id="td-ribbon"):
            for i in range(6):
                with Vertical(classes="td-metric", id=f"td-metric-{i}"):
                    yield Static("", classes="td-metric-k", id=f"td-metric-k-{i}")
                    yield Static("", classes="td-metric-v", id=f"td-metric-v-{i}")
                    yield Static("", classes="td-metric-u", id=f"td-metric-u-{i}")

        with Horizontal(classes="td-trio", id="td-trio"):
            for key in ("flow", "struct", "bandar"):
                with Vertical(classes="td-pulse tone-neutral", id=f"td-pulse-{key}"):
                    yield Static("", classes="td-pulse-title", id=f"td-pulse-t-{key}")
                    yield Static("", classes="td-pulse-head", id=f"td-pulse-h-{key}")
                    yield Static("", classes="td-pulse-sub", id=f"td-pulse-s-{key}")
                    yield Static("", classes="td-pulse-body", id=f"td-pulse-b-{key}")

        with Vertical(classes="td-section", id="td-earn-sec"):
            yield Static(
                "EARNINGS · LAST 4Q          EPS · YOY",
                classes="td-sec-head",
                id="td-earn-head",
            )
            yield Static("", classes="td-earn", id="td-earn-body")

        with Vertical(classes="td-section", id="td-more-sec"):
            yield Static(
                "OWNERSHIP · ANALYST · MORE     collapsed · local",
                classes="td-sec-head",
                id="td-more-head",
            )
            yield Static("", classes="td-sec-body", id="td-more-body")

        yield Static("", classes="td-footer", id="td-footer")

    def paint(self, model: TickerDeskModel) -> None:
        self._model = model
        self.query_one("#td-crumb", Static).update(
            f"View · ticker desk · [bold #f0ebe3]{model.ticker}[/]"
            f"   [#5c6575]local cache · not judgment[/]"
        )
        self.query_one("#td-mark", Static).update(model.ticker)
        self.query_one("#td-name", Static).update(
            f"[bold #c9c3b8]{model.name}[/]" if model.name != "—" else ""
        )
        chips: list[str] = []
        if model.board and model.board != "—":
            chips.append(model.board)
        if model.sector and model.sector != "—":
            chips.append(model.sector)
        if model.tradeable and model.tradeable != "—":
            chips.append(f"[#7ecfb8]{model.tradeable}[/]")
        self.query_one("#td-chips", Static).update(
            "  ".join(f"[#5c6575]{c}[/]" if "[#" not in c else c for c in chips) or "—"
        )
        self.query_one("#td-asof", Static).update(f"as of {model.as_of}")
        fresh = " ".join(model.freshness[:8]) if model.freshness else "freshness —"
        self.query_one("#td-fresh", Static).update(fresh)

        # Mast
        self.query_one("#td-price", Static).update(model.price or "—")
        chg = self.query_one("#td-chg", Static)
        for c in ("pos", "neg"):
            chg.remove_class(c)
        if model.change_1d:
            if model.change_tone in {"pos", "neg"}:
                chg.add_class(model.change_tone)
            chg.update(f" {model.change_1d} ")
        else:
            chg.update("")
        # Decorative tape (density only)
        self.query_one("#td-tape", Static).update("▌▌▌  ▌▌  ▌▌▌▌  ▌  ▌▌▌  ▌▌")

        for i in range(4):
            el = self.query_one(f"#td-hz-{i}", Static)
            if i < len(model.horizons):
                hz = model.horizons[i]
                bar = bar_glyphs(hz.bar_pct, width=8)
                color = {
                    "pos": "#7ecfb8",
                    "neg": "#e87a6e",
                    "neutral": "#8b92a0",
                }.get(hz.tone, "#8b92a0")
                el.update(f"[#5c6575]{hz.label:3}[/] {bar} [{color}]{hz.value}[/]")
            else:
                el.update("")

        for i in range(6):
            if i < len(model.metrics):
                m = model.metrics[i]
                self.query_one(f"#td-metric-k-{i}", Static).update(m.label.upper())
                self.query_one(f"#td-metric-v-{i}", Static).update(m.value)
                self.query_one(f"#td-metric-u-{i}", Static).update(m.unit or "")
            else:
                self.query_one(f"#td-metric-k-{i}", Static).update("")
                self.query_one(f"#td-metric-v-{i}", Static).update("")
                self.query_one(f"#td-metric-u-{i}", Static).update("")

        # Pulses
        by_key = {p.key: p for p in model.pulses}
        for key in ("flow", "struct", "bandar"):
            card = by_key.get(key)
            box = self.query_one(f"#td-pulse-{key}", Vertical)
            for t in ("tone-pos", "tone-neg", "tone-neutral"):
                box.remove_class(t)
            if card is None:
                self.query_one(f"#td-pulse-t-{key}", Static).update(key.upper())
                self.query_one(f"#td-pulse-h-{key}", Static).update("—")
                self.query_one(f"#td-pulse-s-{key}", Static).update("")
                self.query_one(f"#td-pulse-b-{key}", Static).update("")
                box.add_class("tone-neutral")
                continue
            box.add_class(
                f"tone-{card.tone}" if card.tone in {"pos", "neg", "neutral"} else "tone-neutral"
            )
            self.query_one(f"#td-pulse-t-{key}", Static).update(card.title.upper())
            head = self.query_one(f"#td-pulse-h-{key}", Static)
            for c in ("pos", "neg"):
                head.remove_class(c)
            if card.tone in {"pos", "neg"}:
                head.add_class(card.tone)
            head.update(card.headline)
            self.query_one(f"#td-pulse-s-{key}", Static).update(card.sub)
            body_lines = [f"[#5c6575]{k:8}[/] {v}" for k, v in card.rows[:4]]
            self.query_one(f"#td-pulse-b-{key}", Static).update("\n".join(body_lines))

        # Earnings
        if model.earnings:
            earn_lines = []
            for e in model.earnings[:4]:
                bar = bar_glyphs(e.bar_pct, width=10)
                yc = {"pos": "#7ecfb8", "neg": "#e87a6e"}.get(e.yoy_tone, "#8b92a0")
                earn_lines.append(
                    f"[#c9c3b8]{e.period:10}[/] {bar}  [#f0ebe3]{e.eps:>7}[/]  [{yc}]{e.yoy}[/]"
                )
            self.query_one("#td-earn-body", Static).update("\n".join(earn_lines))
            self.query_one("#td-earn-sec", Vertical).display = True
        else:
            self.query_one("#td-earn-body", Static).update(
                "[#5c6575]no earnings rows in local cache[/]"
            )

        # Secondary
        more_lines = [f"[#5c6575]{k:16}[/] [#c9c3b8]{v}[/]" for k, v in model.secondary[:6]]
        self.query_one("#td-more-body", Static).update("\n".join(more_lines) if more_lines else "—")

        self.query_one("#td-footer", Static).update(
            f"[#5c6575]{model.footer}[/]\n[#d4b06a]{model.authority}[/] · Judge stays board Enter"
        )
