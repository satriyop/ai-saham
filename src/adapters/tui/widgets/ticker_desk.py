"""Harga-mast ticker desk — design: docs/design/tui-ticker-desk.html.

Adopt: price is landscape · brass tape · horizon · ribbon · pulse trio ·
earnings · secondary kv. Reject: CLI dump as primary stage.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.ticker_desk_model import (
    FRESH_GRID_SLOTS,
    TickerDeskModel,
    TickerFreshPill,
    bar_glyphs,
)
from src.adapters.tui.widgets.chip_bar import TICKER_JOB_CHIPS, ChipBar
from src.adapters.tui.widgets.flag_chip import FlagChip

# Detail-mode panel inventory (FULL_PANEL_ORDER remainder).
_TICKER_PANEL_FLAGS = (
    "analyst",
    "ownership",
    "sector_macro",
    "corp_actions",
    "insider",
    "seasonality",
    "iev",
    "sentiment",
    "profile",
    "candles",
)
_TICKER_JOB_KEYS = frozenset(k for k, _ in TICKER_JOB_CHIPS)


class TickerDesk(Vertical):
    """Visual ticker instrument — OpenCode price mast."""

    DEFAULT_CSS = """
    TickerDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }

    TickerDesk .td-crumb {
        color: #555555;
        margin-bottom: 1;
        height: auto;
    }

    /* Identity */
    TickerDesk .td-identity {
        height: auto;
        margin-bottom: 1;
        padding: 0 0 1 0;
        border-bottom: solid #1c1c1c;
    }

    TickerDesk .td-mark {
        text-style: bold;
        color: #e8e8e8;
        width: auto;
        padding-right: 2;
    }

    TickerDesk .td-id-sub {
        width: 1fr;
        height: auto;
        color: #d8d8d8;
    }

    TickerDesk .td-fresh-col {
        width: auto;
        height: auto;
        color: #555555;
        text-align: right;
    }

    /* Mock fresh-grid pills */
    TickerDesk .td-fresh-sec {
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-fresh-head {
        color: #555555;
        text-style: bold;
        height: 1;
        margin-bottom: 0;
    }

    TickerDesk .td-fresh-grid {
        height: auto;
        width: 100%;
    }

    TickerDesk .td-fresh-row {
        height: auto;
        width: 100%;
        margin-bottom: 0;
    }

    TickerDesk .td-fp {
        width: 1fr;
        height: auto;
        padding: 0 1;
        margin-right: 1;
        margin-bottom: 0;
        background: #141414;
        border: solid #1c1c1c;
        color: #6b6b6b;
    }

    TickerDesk .td-fp.ok {
        border: solid #1e3a28;
        color: #6fbf8a;
    }

    TickerDesk .td-fp.stale {
        border: solid #3a3220;
        color: #d4b06a;
    }

    TickerDesk .td-fp.miss {
        border: solid #1c1c1c;
        color: #3a3a3a;
    }

    TickerDesk .td-fp.unknown {
        border: solid #1c1c1c;
        color: #6b6b6b;
    }

    /* Mast — price is landscape (mock price-hero) */
    TickerDesk .td-mast {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
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
        color: #c9a68a;
        text-style: bold;
    }

    TickerDesk .td-price-row {
        height: auto;
        margin: 1 0 0 0;
    }

    TickerDesk .td-currency {
        width: auto;
        color: #6b6b6b;
        padding-right: 1;
        content-align: left bottom;
    }

    TickerDesk .td-price {
        width: auto;
        text-style: bold;
        color: #e8e8e8;
        padding-right: 2;
    }

    TickerDesk .td-chg {
        width: auto;
        text-style: bold;
        color: #7a7a7a;
        background: #121212;
        border: solid #2a2a2a;
        padding: 0 1;
        content-align: left middle;
    }

    TickerDesk .td-chg.pos {
        color: #6fbf8a;
        background: #121a14;
        border: solid #1c4038;
    }

    TickerDesk .td-chg.neg {
        color: #c97a72;
        background: #1a1212;
        border: solid #3a2220;
    }

    TickerDesk .td-tape {
        color: #555555;
        height: auto;
        margin-top: 1;
        border-top: solid #1c1c1c;
        padding-top: 0;
    }

    TickerDesk .td-mast-right {
        width: 2fr;
        height: auto;
        border-left: solid #1c1c1c;
        padding-left: 1;
    }

    TickerDesk .td-hz-line {
        height: auto;
        color: #a0a0a0;
    }

    /* Ribbon */
    TickerDesk .td-ribbon {
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-metric {
        width: 1fr;
        background: #141414;
        border: solid #1c1c1c;
        padding: 0 1 1 1;
        margin-right: 1;
        height: auto;
    }

    TickerDesk .td-metric-k {
        color: #6b6b6b;
        text-style: bold;
    }

    TickerDesk .td-metric-v {
        color: #e8e8e8;
        text-style: bold;
    }

    TickerDesk .td-metric-u {
        color: #555555;
    }

    /* Pulse trio */
    TickerDesk .td-trio {
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-pulse {
        width: 1fr;
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #8eb4d8;
        padding: 1 1;
        margin-right: 1;
        height: auto;
        color: #7a7a7a;
    }

    TickerDesk .td-pulse.tone-pos { border-left: solid #6fbf8a; }
    TickerDesk .td-pulse.tone-neg { border-left: solid #c97a72; }
    TickerDesk .td-pulse.tone-neutral { border-left: solid #a89cc9; }

    TickerDesk .td-pulse-title {
        color: #6b6b6b;
        text-style: bold;
    }

    TickerDesk .td-pulse-head {
        color: #e8e8e8;
        text-style: bold;
        height: auto;
    }

    TickerDesk .td-pulse-head.pos { color: #6fbf8a; }
    TickerDesk .td-pulse-head.neg { color: #c97a72; }

    TickerDesk .td-pulse-sub {
        color: #6b6b6b;
        height: auto;
    }

    TickerDesk .td-pulse-body {
        color: #a0a0a0;
        height: auto;
        margin-top: 0;
    }

    /* Earnings */
    TickerDesk .td-section {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #3a4252;
        padding: 1 1;
        margin-bottom: 1;
        height: auto;
    }

    TickerDesk .td-sec-head {
        color: #6b6b6b;
        text-style: bold;
        height: auto;
    }

    TickerDesk .td-earn {
        color: #7a7a7a;
        height: auto;
    }

    TickerDesk .td-sec-body {
        color: #7a7a7a;
        height: auto;
    }

    TickerDesk .td-footer {
        color: #555555;
        height: auto;
        border-top: solid #1c1c1c;
        padding-top: 1;
    }

    TickerDesk .td-sec-body {
        color: #c8c8c8;
        height: auto;
    }

    TickerDesk .td-depth-panel {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 0 1 1 1;
        margin: 0 0 1 0;
        height: auto;
    }

    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._model: TickerDeskModel | None = None
        self._open_flags: set[str] = set()
        self._detail_all: bool = False
        self._active_job: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", classes="td-crumb", id="td-crumb")

        # Chip bar first under crumb: jobs + density · no row label (bible §2)
        yield ChipBar(
            id="td-flags",
            chips=TICKER_JOB_CHIPS,
            chip_id_prefix="td-flag",
            include_detail=True,
            detail_id="td-flag-detail",
            meta_id="td-density-meta",
            meta_text="brief",
        )

        with Horizontal(classes="td-identity", id="td-identity"):
            yield Static("—", classes="td-mark", id="td-mark")
            with Vertical(classes="td-id-sub", id="td-id-sub"):
                yield Static("", id="td-name")
                yield Static("", id="td-chips")
            with Vertical(classes="td-fresh-col", id="td-fresh-col"):
                yield Static("", id="td-asof")
                yield Static("", id="td-fresh")

        # Mock fresh-grid (Price · Flow · Bandar · …)
        with Vertical(classes="td-fresh-sec", id="td-fresh-sec"):
            yield Static("FRESHNESS", classes="td-fresh-head", id="td-fresh-head")
            with Vertical(classes="td-fresh-grid", id="td-fresh-grid"):
                # 2 rows × 5 pills = 10 mock slots
                for row in range(2):
                    with Horizontal(classes="td-fresh-row", id=f"td-fresh-row-{row}"):
                        for col in range(5):
                            idx = row * 5 + col
                            yield Static(
                                "",
                                id=f"td-fp-{idx}",
                                classes="td-fp miss",
                            )

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
                "MORE · local panels",
                classes="td-sec-head",
                id="td-more-head",
            )
            # Precomposed depth panels (mock cli-stack) — filled on paint
            with Vertical(id="td-depth-stack"):
                for key in _TICKER_PANEL_FLAGS:
                    with Vertical(classes="td-depth-panel", id=f"td-depth-{key}"):
                        yield Static("", id=f"td-depth-t-{key}", classes="td-sec-head")
                        yield Static("", id=f"td-depth-b-{key}", classes="td-sec-body")
            yield Static("", classes="td-sec-body", id="td-more-body")

        yield Static("", classes="td-footer", id="td-footer")

    def on_flag_chip_selected(self, event: FlagChip.Selected) -> None:
        event.stop()
        key = event.flag_key
        if key in _TICKER_JOB_KEYS:
            try:
                app = self.app
            except Exception:
                return
            if hasattr(app, "action_ticker_job"):
                app.action_ticker_job(key)  # type: ignore[attr-defined]
            return
        if self._model is None:
            return
        if key != "detail":
            return
        self._detail_all = not self._detail_all
        self._open_flags = set(self._available_panels(self._model)) if self._detail_all else set()
        self.paint(self._model, detail_open=self._detail_all, sync_from_detail=False)
        try:
            app = self.app
            if hasattr(app, "_ticker_detail_open"):
                app._ticker_detail_open = self._detail_all  # type: ignore[attr-defined]
        except Exception:
            pass

    def set_active_job(self, job: str | None) -> None:
        """Highlight job chip when a sibling job stage is open."""
        self._active_job = job
        if self._model is not None:
            self.paint(self._model, detail_open=self._detail_all, sync_from_detail=False)
        else:
            self._paint_chip_bar()

    def _available_panels(self, model: TickerDeskModel) -> set[str]:
        return {
            p.key
            for p in model.detail_panels
            if p.key in _TICKER_PANEL_FLAGS and p.status == "present"
        }

    def _paint_fresh_grid(self, pills: tuple[TickerFreshPill, ...]) -> None:
        """Paint mock fresh-grid pills (ok / stale / miss)."""
        for idx in range(FRESH_GRID_SLOTS):
            el = self.query_one(f"#td-fp-{idx}", Static)
            for kind in ("ok", "stale", "miss", "unknown"):
                el.remove_class(kind)
            if idx < len(pills):
                pill = pills[idx]
                kind = pill.css_kind
                el.add_class(kind)
                val_col = {
                    "ok": "#6fbf8a",
                    "stale": "#d4b06a",
                    "miss": "#3a3a3a",
                    "unknown": "#6b6b6b",
                }.get(kind, "#6b6b6b")
                el.update(f"[#555555]{pill.label}[/]  [{val_col}]{pill.value}[/]")
            else:
                el.add_class("miss")
                el.update("")

    def paint(
        self,
        model: TickerDeskModel,
        *,
        detail_open: bool = False,
        sync_from_detail: bool = True,
    ) -> None:
        self._model = model
        if sync_from_detail:
            self._detail_all = detail_open
            if detail_open:
                self._open_flags = set(self._available_panels(model))
            else:
                self._open_flags.clear()
        open_flags = set(self._open_flags)
        if self._detail_all:
            open_flags |= self._available_panels(model)
        detail_open = self._detail_all or bool(open_flags)
        density = "detail" if self._detail_all else "brief"
        self.query_one("#td-crumb", Static).update(
            f"View · ticker · [bold #e8e8e8]{model.ticker}[/]   "
            f"[#555555]{density} · local cache · browse[/]"
        )
        self.query_one("#td-mark", Static).update(model.ticker)
        self.query_one("#td-name", Static).update(
            f"[bold #d8d8d8]{model.name}[/]" if model.name != "—" else ""
        )
        chips: list[str] = []
        if model.board and model.board != "—":
            chips.append(model.board)
        if model.sector and model.sector != "—":
            chips.append(model.sector)
        if model.tradeable and model.tradeable != "—":
            chips.append(f"[#6fbf8a]{model.tradeable}[/]")
        self.query_one("#td-chips", Static).update(
            "  ".join(f"[#555555]{c}[/]" if "[#" not in c else c for c in chips) or "—"
        )
        self.query_one("#td-asof", Static).update(f"as of {model.as_of}")
        # Compact summary still on identity column
        ok_n = sum(1 for p in model.freshness if p.status == "ok")
        self.query_one("#td-fresh", Static).update(
            f"{ok_n}/{len(model.freshness)} ok" if model.freshness else "freshness —"
        )
        self._paint_fresh_grid(model.freshness)

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
                    "pos": "#6fbf8a",
                    "neg": "#c97a72",
                    "neutral": "#7a7a7a",
                }.get(hz.tone, "#7a7a7a")
                el.update(f"[#555555]{hz.label:3}[/] {bar} [{color}]{hz.value}[/]")
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
            body_lines = [f"[#555555]{k:8}[/] {v}" for k, v in card.rows[:4]]
            self.query_one(f"#td-pulse-b-{key}", Static).update("\n".join(body_lines))

        # Earnings
        if model.earnings:
            earn_lines = []
            for e in model.earnings[:4]:
                bar = bar_glyphs(e.bar_pct, width=10)
                yc = {"pos": "#6fbf8a", "neg": "#c97a72"}.get(e.yoy_tone, "#7a7a7a")
                earn_lines.append(
                    f"[#d8d8d8]{e.period:10}[/] {bar}  [#e8e8e8]{e.eps:>7}[/]  [{yc}]{e.yoy}[/]"
                )
            self.query_one("#td-earn-body", Static).update("\n".join(earn_lines))
            self.query_one("#td-earn-sec", Vertical).display = True
        else:
            self.query_one("#td-earn-body", Static).update(
                "[#555555]no earnings rows in local cache[/]"
            )

        # Detail inventory (BRIEF collapses; detail · d expands)
        head = self.query_one("#td-more-head", Static)
        by_panel = {p.key: p for p in model.detail_panels}
        depth_open = self._detail_all or bool(open_flags)
        more_sec = self.query_one("#td-more-sec", Vertical)
        if depth_open:
            more_sec.display = True
            head.update("DETAIL · full inventory · d · local cache")
            self.query_one("#td-more-body", Static).update("")
            self.query_one("#td-more-body", Static).display = False
            for key in _TICKER_PANEL_FLAGS:
                panel_el = self.query_one(f"#td-depth-{key}", Vertical)
                p = by_panel.get(key)
                show = self._detail_all or key in open_flags
                if not show or p is None:
                    panel_el.display = False
                    continue
                panel_el.display = True
                if p.status == "present":
                    st = "[#6fbf8a]present[/]"
                elif p.status == "missing":
                    st = "[#555555]missing[/]"
                else:
                    st = f"[#555555]{p.status}[/]"
                self.query_one(f"#td-depth-t-{key}", Static).update(
                    f"[bold #d8d8d8]{p.title.upper()}[/]  {st}"
                )
                body_lines = list(p.lines[:8]) if p.lines else ["—"]
                self.query_one(f"#td-depth-b-{key}", Static).update(
                    "\n".join(f"  {ln}" for ln in body_lines)
                )
        else:
            # Brief default: hide extended inventory wall
            more_sec.display = False
            for key in _TICKER_PANEL_FLAGS:
                self.query_one(f"#td-depth-{key}", Vertical).display = False

        self._paint_chip_bar()

        foot = model.footer or ""
        foot = foot.replace("d detail", "d detail").replace("d collapse", "d detail")
        if "d detail" not in foot and "b f o x n" not in foot:
            foot = f"b f o x n jobs · d detail · {foot}".strip(" ·")
        if self._detail_all:
            foot = foot.replace("d detail", "d brief", 1)
        self.query_one("#td-footer", Static).update(
            f"[#555555]{foot}[/]\n[#d4b06a]{model.authority}[/]"
        )

    def _paint_chip_bar(self) -> None:
        on_keys: set[str] = set()
        if self._detail_all:
            on_keys.add("detail")
        if self._active_job:
            on_keys.add(self._active_job)
        try:
            bar = self.query_one("#td-flags", ChipBar)
            bar.paint_states(on_keys=on_keys)
            bar.set_meta("detail" if self._detail_all else "brief")
        except Exception:
            try:
                self.query_one("#td-flag-detail", FlagChip).set_chip_state(
                    available=True, expanded=self._detail_all
                )
            except Exception:
                pass
