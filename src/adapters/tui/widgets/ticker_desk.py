"""Harga-mast ticker desk — design: docs/design/tui-ticker-desk.html.

Adopt: price is landscape · brass tape · horizon · ribbon · pulse trio ·
earnings · secondary kv. Reject: CLI dump as primary stage.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.shared.ticker_dist_desk_model import DistSideRow, TickerDistDeskModel
from src.adapters.shared.ticker_flow_desk_model import TickerFlowDeskModel
from src.adapters.shared.ticker_foreign_desk_model import TickerForeignDeskModel
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
        height: 3;
        width: 100%;
        margin: 1 0 0 0;
        align: left middle;
    }

    TickerDesk .td-currency {
        width: auto;
        height: 3;
        color: #6b6b6b;
        padding-right: 1;
        content-align: left middle;
    }

    TickerDesk .td-price {
        width: auto;
        height: 3;
        text-style: bold;
        color: #e8e8e8;
        padding-right: 2;
        content-align: left middle;
    }

    TickerDesk .td-chg {
        width: auto;
        height: 3;
        text-style: bold;
        color: #7a7a7a;
        background: #121212;
        border: solid #2a2a2a;
        padding: 0 1;
        content-align: center middle;
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

    TickerDesk .td-mast-right {
        width: 2fr;
        height: auto;
        border-left: solid #1c1c1c;
        padding-left: 1;
    }

    TickerDesk .td-hz-line {
        height: auto;
        color: #a0a0a0;
        margin-bottom: 0;
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

    /* Earnings + secondary side-by-side */
    TickerDesk .td-earn-row {
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-section {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #3a4252;
        padding: 1 1;
        margin-bottom: 1;
        height: auto;
    }

    TickerDesk .td-earn-panel {
        width: 3fr;
        margin-right: 1;
        margin-bottom: 0;
    }

    TickerDesk .td-secondary-panel {
        width: 2fr;
        margin-bottom: 0;
        border-left: solid #4a5568;
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

    TickerDesk .td-secondary {
        color: #a0a0a0;
        height: auto;
    }

    TickerDesk .td-sec-body {
        color: #c8c8c8;
        height: auto;
    }

    TickerDesk .td-footer {
        color: #555555;
        height: auto;
        border-top: solid #1c1c1c;
        padding-top: 1;
    }

    TickerDesk .td-depth-panel {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 0 1 1 1;
        margin: 0 0 1 0;
        height: auto;
    }

    /* Flow job desk (design hero · pulses · sessions) */
    TickerDesk .td-job-shell {
        border-left: solid #c9a68a;
    }

    TickerDesk .td-flow-desk {
        height: auto;
        margin-top: 0;
    }

    TickerDesk .td-flow-lab {
        color: #6b6b6b;
        text-style: bold;
        height: auto;
    }

    TickerDesk .td-flow-big {
        color: #e8e8e8;
        text-style: bold;
        height: auto;
        margin: 0 0 0 0;
    }

    TickerDesk .td-flow-big.pos { color: #6fbf8a; }
    TickerDesk .td-flow-big.neg { color: #c97a72; }

    TickerDesk .td-flow-sub {
        color: #555555;
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-flow-pulses {
        height: auto;
        margin-bottom: 1;
    }

    TickerDesk .td-flow-pulse {
        width: 1fr;
        background: #101010;
        border: solid #1c1c1c;
        padding: 0 1;
        margin-right: 1;
        height: auto;
    }

    TickerDesk .td-flow-pk {
        color: #555555;
        height: auto;
    }

    TickerDesk .td-flow-pv {
        color: #e8e8e8;
        text-style: bold;
        height: auto;
    }

    TickerDesk .td-flow-pv.pos { color: #6fbf8a; }
    TickerDesk .td-flow-pv.neg { color: #c97a72; }

    TickerDesk .td-flow-days {
        color: #a0a0a0;
        height: auto;
    }

    TickerDesk .td-flow-story {
        color: #555555;
        height: auto;
        margin-top: 1;
    }

    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._model: TickerDeskModel | None = None
        self._open_flags: set[str] = set()
        self._detail_all: bool = False
        self._active_job: str | None = None
        self._job_title: str = ""
        self._job_body: str = ""
        self._job_desk: (
            TickerFlowDeskModel | TickerForeignDeskModel | TickerDistDeskModel | None
        ) = None

    def compose(self) -> ComposeResult:
        yield Static("", classes="td-crumb", id="td-crumb")

        # Chip bar first under crumb: jobs + density · no row label (bible §2)
        yield ChipBar(
            id="td-flags",
            chips=TICKER_JOB_CHIPS,
            chip_id_prefix="td-flag",
            include_detail=True,
            detail_id="td-flag-detail",
        )

        # Job sub-stage (structured flow desk + flat body fallback)
        with Vertical(classes="td-section td-job-shell", id="td-job-sec"):
            yield Static("", classes="td-sec-head", id="td-job-head")
            with Vertical(classes="td-flow-desk", id="td-flow-desk"):
                yield Static("", classes="td-flow-lab", id="td-flow-lab")
                yield Static("", classes="td-flow-big", id="td-flow-big")
                yield Static("", classes="td-flow-sub", id="td-flow-sub")
                with Horizontal(classes="td-flow-pulses", id="td-flow-pulses"):
                    for i in range(4):
                        with Vertical(classes="td-flow-pulse", id=f"td-flow-p-{i}"):
                            yield Static("", classes="td-flow-pk", id=f"td-flow-pk-{i}")
                            yield Static("", classes="td-flow-pv", id=f"td-flow-pv-{i}")
                yield Static("SESSIONS", classes="td-sec-head", id="td-flow-days-head")
                yield Static("", classes="td-flow-days", id="td-flow-days")
                yield Static("", classes="td-flow-story", id="td-flow-story")
            yield Static("", classes="td-sec-body", id="td-job-body")

        with Horizontal(classes="td-identity", id="td-identity"):
            yield Static("—", classes="td-mark", id="td-mark")
            with Vertical(classes="td-id-sub", id="td-id-sub"):
                yield Static("", id="td-name")
                yield Static("", id="td-chips")
            with Vertical(classes="td-fresh-col", id="td-fresh-col"):
                yield Static("", id="td-asof")
                yield Static("", id="td-fresh")

        # Freshness: slots for real pills only (no Sent; unused hidden on paint)
        with Vertical(classes="td-fresh-sec", id="td-fresh-sec"):
            yield Static("FRESHNESS", classes="td-fresh-head", id="td-fresh-head")
            with Vertical(classes="td-fresh-grid", id="td-fresh-grid"):
                # Up to FRESH_GRID_SLOTS statics (3×4); paint shows only real pills
                for row in range(3):
                    with Horizontal(classes="td-fresh-row", id=f"td-fresh-row-{row}"):
                        for col in range(4):
                            idx = row * 4 + col
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

        with Horizontal(classes="td-earn-row", id="td-earn-row"):
            with Vertical(classes="td-section td-earn-panel", id="td-earn-sec"):
                yield Static(
                    "EARNINGS · LAST 4Q · EPS · YOY",
                    classes="td-sec-head",
                    id="td-earn-head",
                )
                yield Static("", classes="td-earn", id="td-earn-body")
            with Vertical(classes="td-section td-secondary-panel", id="td-secondary-sec"):
                yield Static(
                    "SECONDARY · LOCAL PANELS",
                    classes="td-sec-head",
                    id="td-secondary-head",
                )
                yield Static("", classes="td-secondary", id="td-secondary-body")

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
        self.set_job_view(job)

    def set_job_view(
        self,
        job: str | None,
        *,
        title: str = "",
        body: str = "",
        desk: TickerFlowDeskModel | TickerForeignDeskModel | TickerDistDeskModel | None = None,
    ) -> None:
        """Show/hide job body under chip bar (browse-only CLI sibling)."""
        self._active_job = job
        self._job_title = title or ""
        self._job_body = body or ""
        self._job_desk = desk if job else None
        if self._model is not None:
            self.paint(self._model, detail_open=self._detail_all, sync_from_detail=False)
        else:
            self._paint_job_and_chips_only()

    def _available_panels(self, model: TickerDeskModel) -> set[str]:
        return {
            p.key
            for p in model.detail_panels
            if p.key in _TICKER_PANEL_FLAGS and p.status == "present"
        }

    def _paint_fresh_grid(self, pills: tuple[TickerFreshPill, ...]) -> None:
        """Paint **real** freshness pills only — no Sent, no fake empty tiles."""
        sec = self.query_one("#td-fresh-sec", Vertical)
        if not pills:
            # Honest empty: one line, not a grid of invented misses
            sec.display = True
            self.query_one("#td-fresh-head", Static).update("FRESHNESS")
            for idx in range(FRESH_GRID_SLOTS):
                try:
                    el = self.query_one(f"#td-fp-{idx}", Static)
                    el.display = idx == 0
                    if idx == 0:
                        for kind in ("ok", "stale", "miss", "unknown"):
                            el.remove_class(kind)
                        el.add_class("miss")
                        el.update("[#555555]freshness[/]  [#3a3a3a]not cached[/]")
                except Exception:
                    pass
            return
        sec.display = True
        self.query_one("#td-fresh-head", Static).update("FRESHNESS")
        for idx in range(FRESH_GRID_SLOTS):
            try:
                el = self.query_one(f"#td-fp-{idx}", Static)
            except Exception:
                continue
            for kind in ("ok", "stale", "miss", "unknown"):
                el.remove_class(kind)
            if idx < len(pills):
                pill = pills[idx]
                kind = pill.css_kind
                el.display = True
                el.add_class(kind)
                val_col = {
                    "ok": "#6fbf8a",
                    "stale": "#d4b06a",
                    "miss": "#3a3a3a",
                    "unknown": "#6b6b6b",
                }.get(kind, "#6b6b6b")
                el.update(f"[#555555]{pill.label}[/]  [{val_col}]{pill.value}[/]")
            else:
                el.display = False
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
        # Density state = [d] is-on only — never restate brief/detail in crumb
        if self._active_job:
            self.query_one("#td-crumb", Static).update(
                f"View · ticker · [bold #e8e8e8]{model.ticker}[/]   "
                f"[#555555]{self._active_job} · local cache · browse[/]"
            )
        else:
            self.query_one("#td-crumb", Static).update(
                f"View · ticker · [bold #e8e8e8]{model.ticker}[/]   "
                f"[#555555]local cache · browse[/]"
            )
        job_mode = bool(self._active_job and (self._job_body or self._job_desk is not None))
        self._set_show_panels_visible(not job_mode)
        if job_mode:
            job_sec = self.query_one("#td-job-sec", Vertical)
            job_sec.display = True
            self.query_one("#td-job-head", Static).update(
                (self._job_title or self._active_job or "job").upper()
            )
            self._paint_job_body()
            self._paint_chip_bar()
            foot = "esc show · chips switch job · b f o x n · browse only"
            if self._job_desk is not None and getattr(self._job_desk, "footer", None):
                foot = self._job_desk.footer
            self.query_one("#td-footer", Static).update(
                f"[#555555]{foot}[/]\n[#d4b06a]{model.authority}[/]"
            )
            return
        try:
            self.query_one("#td-job-sec", Vertical).display = False
        except Exception:
            pass
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

        # Mast — real last + chg only (no decorative tape / fake sparkline)
        self.query_one("#td-price", Static).update(model.price or "—")
        chg = self.query_one("#td-chg", Static)
        for c in ("pos", "neg"):
            chg.remove_class(c)
        chg_txt = (model.change_1d or "").strip()
        if chg_txt and chg_txt not in {"—", "-", "–"}:
            if model.change_tone in {"pos", "neg"}:
                chg.add_class(model.change_tone)
            # Real 1d change; badge sits on same baseline as price
            label = chg_txt if "1d" in chg_txt.lower() else f"{chg_txt} 1d"
            chg.update(f" {label} ")
            chg.display = True
        else:
            chg.update("")
            chg.display = False

        for i in range(4):
            el = self.query_one(f"#td-hz-{i}", Static)
            if i < len(model.horizons):
                hz = model.horizons[i]
                color = {
                    "pos": "#6fbf8a",
                    "neg": "#c97a72",
                    "neutral": "#a0a0a0",
                }.get(hz.tone, "#a0a0a0")
                val = (hz.value or "—").strip() or "—"
                if val in {"—", "-", "–"}:
                    # Honest empty horizon — no grey wallpaper bar
                    el.update(f"[#555555]{hz.label:3}[/]  [#555555]—[/]")
                else:
                    # Filled bar only (tone-colored); no hollow ░ fake fill
                    bar = bar_glyphs(hz.bar_pct, width=8, hollow=False)
                    if bar:
                        el.update(f"[#555555]{hz.label:3}[/] [{color}]{bar}[/]  [{color}]{val}[/]")
                    else:
                        el.update(f"[#555555]{hz.label:3}[/]  [{color}]{val}[/]")
                el.display = True
            else:
                el.update("")
                el.display = False

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

        # Earnings — real EPS · YoY%; solid bar = relative |EPS| (no hollow ░)
        earn_sec = self.query_one("#td-earn-sec", Vertical)
        earn_sec.display = True
        if model.earnings:
            head = (
                f"[#555555]{'Period':8}[/]  {'':12}  [#555555]{'EPS':>7}[/]  "
                f"[#555555]{'YoY':>10}[/]"
            )
            earn_lines = [head]
            any_extreme = False
            for e in model.earnings[:4]:
                bar = bar_glyphs(e.bar_pct, width=12, hollow=False)
                # Tone bar by YoY; warn = amber (extreme / non-comparable base)
                if e.yoy_tone == "pos":
                    bc = "#6fbf8a"
                elif e.yoy_tone == "neg":
                    bc = "#c97a72"
                elif e.yoy_tone == "warn":
                    bc = "#d4b06a"
                else:
                    bc = "#6b6b6b"
                pad = max(0, 12 - len(bar))
                bar_s = f"[{bc}]{bar}[/]{' ' * pad}" if bar else f"{'':12}"
                yc = {
                    "pos": "#6fbf8a",
                    "neg": "#c97a72",
                    "warn": "#d4b06a",
                }.get(e.yoy_tone, "#7a7a7a")
                if getattr(e, "yoy_extreme", False):
                    any_extreme = True
                earn_lines.append(
                    f"[#d8d8d8]{e.period:8}[/]  {bar_s}  [#e8e8e8]{e.eps:>7}[/]  "
                    f"[{yc}]{e.yoy:>10}[/]"
                )
            if any_extreme:
                earn_lines.append(
                    "[#555555]* YoY uses reported prior-year EPS — extreme % often "
                    "split / restatement, not pure growth[/]"
                )
            self.query_one("#td-earn-head", Static).update("EARNINGS · LAST 4Q · EPS · YOY")
            self.query_one("#td-earn-body", Static).update("\n".join(earn_lines))
        else:
            self.query_one("#td-earn-head", Static).update("EARNINGS · LAST 4Q")
            self.query_one("#td-earn-body", Static).update(
                "[#555555]no earnings rows in local cache[/]"
            )

        # Secondary — presence-only inventory (design hierarchy · not CLI dump)
        sec = self.query_one("#td-secondary-sec", Vertical)
        sec.display = True
        if model.secondary:
            sec_lines = [
                f"[#555555]{str(k):12}[/]  [#c8c8c8]{v}[/]" for k, v in model.secondary[:8]
            ]
            self.query_one("#td-secondary-head", Static).update("SECONDARY · LOCAL PANELS")
            self.query_one("#td-secondary-body", Static).update("\n".join(sec_lines))
        else:
            self.query_one("#td-secondary-head", Static).update("SECONDARY")
            self.query_one("#td-secondary-body", Static).update(
                "[#555555]no secondary inventory[/]"
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
        if self._detail_all and not self._active_job:
            on_keys.add("detail")
        if self._active_job:
            on_keys.add(self._active_job)
        try:
            bar = self.query_one("#td-flags", ChipBar)
            bar.paint_states(on_keys=on_keys)
        except Exception:
            try:
                self.query_one("#td-flag-detail", FlagChip).set_chip_state(
                    available=True, expanded=self._detail_all and not self._active_job
                )
            except Exception:
                pass

    def _set_show_panels_visible(self, visible: bool) -> None:
        for sid in (
            "td-identity",
            "td-fresh-sec",
            "td-mast",
            "td-ribbon",
            "td-trio",
            "td-earn-row",
            "td-earn-sec",
            "td-secondary-sec",
            "td-more-sec",
        ):
            try:
                self.query_one(f"#{sid}").display = visible
            except Exception:
                pass

    def _paint_job_body(self) -> None:
        """Paint structured job desk when present; else flat body (loading / other jobs)."""
        shell_el = None
        try:
            shell_el = self.query_one("#td-flow-desk", Vertical)
        except Exception:
            shell_el = None

        flow_ok = isinstance(self._job_desk, TickerFlowDeskModel) and self._active_job == "flow"
        foreign_ok = (
            isinstance(self._job_desk, TickerForeignDeskModel) and self._active_job == "foreign"
        )
        dist_ok = isinstance(self._job_desk, TickerDistDeskModel) and self._active_job == "dist"

        if flow_ok or foreign_ok or dist_ok:
            if shell_el is not None:
                shell_el.display = True
            try:
                self.query_one("#td-job-body", Static).display = False
            except Exception:
                pass
            if flow_ok:
                assert isinstance(self._job_desk, TickerFlowDeskModel)
                self._paint_flow_desk(self._job_desk)
            elif foreign_ok:
                assert isinstance(self._job_desk, TickerForeignDeskModel)
                self._paint_foreign_desk(self._job_desk)
            else:
                assert isinstance(self._job_desk, TickerDistDeskModel)
                self._paint_dist_desk(self._job_desk)
            return

        if shell_el is not None:
            shell_el.display = False
        try:
            body_el = self.query_one("#td-job-body", Static)
            body_el.display = True
            body_el.update(self._job_body or "")
        except Exception:
            pass

    def _paint_job_hero_pulses(
        self,
        desk: TickerFlowDeskModel | TickerForeignDeskModel | TickerDistDeskModel,
    ) -> None:
        """Shared hero + 4-pulse chrome for structured job desks."""
        self.query_one("#td-flow-lab", Static).update(desk.hero_lab)
        big = self.query_one("#td-flow-big", Static)
        for c in ("pos", "neg"):
            big.remove_class(c)
        if desk.hero_tone in {"pos", "neg"}:
            big.add_class(desk.hero_tone)
        big.update(desk.hero_big)
        self.query_one("#td-flow-sub", Static).update(desk.hero_sub)

        for i in range(4):
            pk = self.query_one(f"#td-flow-pk-{i}", Static)
            pv = self.query_one(f"#td-flow-pv-{i}", Static)
            for c in ("pos", "neg"):
                pv.remove_class(c)
            if i < len(desk.pulses):
                p = desk.pulses[i]
                pk.update(p.label.upper())
                if p.tone in {"pos", "neg"}:
                    pv.add_class(p.tone)
                pv.update(p.value)
            else:
                pk.update("")
                pv.update("")

        story = (desk.story or "").replace("\n", " · ")
        self.query_one("#td-flow-story", Static).update(f"[#555555]{story}[/]" if story else "")

    def _paint_flow_desk(self, desk: TickerFlowDeskModel) -> None:
        """Design lock: hero · 4 pulses · sessions table · real nets only."""
        self._paint_job_hero_pulses(desk)

        if desk.empty or not desk.days:
            self.query_one("#td-flow-days-head", Static).update("SESSIONS")
            self.query_one("#td-flow-days", Static).update(
                f"[#555555]no sessions · {desk.fetch_hint}[/]"
            )
            return

        self.query_one("#td-flow-days-head", Static).update(
            f"SESSIONS · {len(desk.days)} · NEWEST FIRST"
        )
        head = (
            f"[#555555]{'Date':10}[/]  {'':10}  [#555555]{'Net':>10}[/]  "
            f"[#555555]{'Ratio':>7}[/]  [#555555]{'Buyer':>6}[/]  [#555555]{'Seller':>6}[/]"
        )
        lines = [head]
        for d in desk.days:
            tone = {"pos": "#6fbf8a", "neg": "#c97a72"}.get(d.net_tone, "#a0a0a0")
            bar = bar_glyphs(d.bar_pct, width=10, hollow=False)
            pad = max(0, 10 - len(bar))
            bar_s = f"[{tone}]{bar}[/]{' ' * pad}" if bar else f"{'':10}"
            lines.append(
                f"[#d8d8d8]{d.date_s:10}[/]  {bar_s}  [{tone}]{d.net_s:>10}[/]  "
                f"[#7a7a7a]{d.ratio_s:>7}[/]  [#c8c8c8]{d.buyer:>6}[/]  "
                f"[#c8c8c8]{d.seller:>6}[/]"
            )
        self.query_one("#td-flow-days", Static).update("\n".join(lines))

    def _paint_foreign_desk(self, desk: TickerForeignDeskModel) -> None:
        """Design lock: hero · 5d/20d/days/source · daily points (net · lot · avg)."""
        self._paint_job_hero_pulses(desk)

        if desk.empty or not desk.days:
            self.query_one("#td-flow-days-head", Static).update("DAILY POINTS")
            self.query_one("#td-flow-days", Static).update(
                f"[#555555]no points · {desk.fetch_hint}[/]"
            )
            return

        self.query_one("#td-flow-days-head", Static).update(
            f"DAILY POINTS · {len(desk.days)} · NEWEST FIRST"
        )
        head = (
            f"[#555555]{'Date':10}[/]  {'':8}  [#555555]{'Source':10}[/]  "
            f"[#555555]{'Net':>10}[/]  [#555555]{'Lot':>10}[/]  [#555555]{'Avg':>8}[/]"
        )
        lines = [head]
        for d in desk.days:
            tone = {"pos": "#6fbf8a", "neg": "#c97a72"}.get(d.net_tone, "#a0a0a0")
            bar = bar_glyphs(d.bar_pct, width=8, hollow=False)
            pad = max(0, 8 - len(bar))
            bar_s = f"[{tone}]{bar}[/]{' ' * pad}" if bar else f"{'':8}"
            lines.append(
                f"[#d8d8d8]{d.date_s:10}[/]  {bar_s}  [#7a7a7a]{d.source:10}[/]  "
                f"[{tone}]{d.net_s:>10}[/]  [#c8c8c8]{d.lot_s:>10}[/]  "
                f"[#c8c8c8]{d.avg_s:>8}[/]"
            )
        self.query_one("#td-flow-days", Static).update("\n".join(lines))

    def _paint_dist_desk(self, desk: TickerDistDeskModel) -> None:
        """Design lock: hero · pulses · dual heat buyers/sellers · F/L tags · share bars."""
        self._paint_job_hero_pulses(desk)

        if desk.empty and not desk.buyers and not desk.sellers:
            self.query_one("#td-flow-days-head", Static).update("DUAL HEAT · COUNTERPARTIES")
            self.query_one("#td-flow-days", Static).update(
                f"[#555555]no distribution · {desk.fetch_hint}[/]"
            )
            return

        self.query_one("#td-flow-days-head", Static).update(
            "DUAL HEAT · TOP BUYERS / TOP SELLERS · F=Foreign L=Local"
        )
        mint = "#6fbf8a"
        coral = "#c97a72"
        lines: list[str] = []

        def _side_block(
            title: str,
            sides: tuple[DistSideRow, ...],
            *,
            arrow: str,
            head_color: str,
        ) -> None:
            lines.append(f"[{head_color}]{title}[/]")
            if not sides:
                lines.append("[#555555]  — empty side[/]")
                lines.append("")
                return
            for s in sides:
                tag_c = {"F": "#7aa2c4", "L": "#a0a0a0", "G": "#d4b06a"}.get(s.type_tag, "#a0a0a0")
                lines.append(
                    f"  [#e8e8e8]{s.rank}[/] [bold #d8d8d8]{s.code}[/]"
                    f"[{tag_c}]\\[{s.type_tag}][/]  [{head_color}]{s.amount_s}[/]"
                )
                for cp in s.cps:
                    bar = bar_glyphs(cp.bar_pct, width=8, hollow=False)
                    pad = max(0, 8 - len(bar))
                    bar_s = f"[{head_color}]{bar}[/]{' ' * pad}" if bar else f"{'':8}"
                    ctag_c = {"F": "#7aa2c4", "L": "#a0a0a0", "G": "#d4b06a"}.get(
                        cp.type_tag, "#a0a0a0"
                    )
                    lines.append(
                        f"    [#555555]{arrow}[/] [#c8c8c8]{cp.code}[/]"
                        f"[{ctag_c}]\\[{cp.type_tag}][/]  "
                        f"[#c8c8c8]{cp.amount_s}[/]  [#7a7a7a]{cp.pct}%[/]  {bar_s}"
                    )
            lines.append("")

        _side_block(
            "TOP BUYERS · bought FROM →",
            desk.buyers,
            arrow="←",
            head_color=mint,
        )
        _side_block(
            "TOP SELLERS · sold TO →",
            desk.sellers,
            arrow="→",
            head_color=coral,
        )
        self.query_one("#td-flow-days", Static).update("\n".join(lines))

    def _paint_job_and_chips_only(self) -> None:
        """When model not yet painted, still show job body + chips."""
        try:
            job_sec = self.query_one("#td-job-sec", Vertical)
            if self._active_job and (self._job_body or self._job_desk is not None):
                job_sec.display = True
                self.query_one("#td-job-head", Static).update(
                    (self._job_title or self._active_job or "job").upper()
                )
                self._paint_job_body()
                self._set_show_panels_visible(False)
            else:
                job_sec.display = False
                self._set_show_panels_visible(True)
        except Exception:
            pass
        self._paint_chip_bar()
