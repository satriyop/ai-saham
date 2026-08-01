"""Harga-mast ticker desk — design: docs/design/tui-ticker-desk.html.

Adopt: price is landscape · brass tape · horizon · ribbon · pulse trio ·
earnings · secondary kv. Reject: CLI dump as primary stage.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.shared.ticker_brokers_desk_model import TickerBrokersDeskModel
from src.adapters.shared.ticker_dist_desk_model import DistSideRow, TickerDistDeskModel
from src.adapters.shared.ticker_fin_desk_model import TickerFinDeskModel
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

# Depth card line labels (design cockpit cli-panel · dim k / bright v)
_DEPTH_LABELS = (
    "Target",
    "Range",
    "Top Holder",
    "Institutional",
    "Individual",
    "Total Shares",
    "Report Date",
    "Sector",
    "Regime",
    "Peers up 5d",
    "Rel strength",
    "Web",
    "Email",
    "About",
    "Name",
    "Board",
    "IPO",
    "IPO price",
    "Listed",
    "Pattern",
    "Edge",
    "Window",
    "Note",
    "Summary",
    "Updated",
    "Fetched",
)


def _paint_depth_fact_line(ln: str) -> str:
    """OpenCode card line: mute label · fog value · mint/coral for signed/BUY/SELL.

    Mirrors cockpit ``.cli-panel .body .line`` (dim k / bright v / pos|neg).
    """
    s = (ln or "").strip()
    if not s:
        return ""

    # Mini-table header row — mute like mock ``th``
    if s.startswith("Date ") and any(
        h in s for h in ("Type", "Name", "Open", "IEP", "IEV", "Detail", "Action")
    ):
        return f"[#555555]{s}[/]"

    # Table / mono data rows (candles, IEV, insider, corp)
    looks_table = s[:10].count("-") >= 2 or (len(s) > 12 and s[0].isdigit() and "  " in s)
    if looks_table or (
        "  " not in s[:20]
        and any(ch.isdigit() for ch in s[:12])
        and not s.startswith("Target")
        and "→" not in s
    ):
        if " BUY" in f" {s}" or s.endswith(" BUY") or " BUY " in s:
            return f"[#6fbf8a]{s}[/]"
        if " SELL" in f" {s}" or s.endswith(" SELL") or " SELL " in s:
            return f"[#c97a72]{s}[/]"
        return f"[#c8c8c8]{s}[/]"

    lab = None
    rest = s
    for prefix in _DEPTH_LABELS:
        if s.startswith(prefix) and (len(s) == len(prefix) or s[len(prefix)] in " \t"):
            lab = prefix
            rest = s[len(prefix) :].strip()
            break
    if lab is None and "  " in s:
        lab, _, rest = s.partition("  ")
        lab, rest = lab.strip(), rest.strip()

    tone = "#e8e8e8"
    u = (rest or s).upper()
    if "→ BUY" in s.upper() or s.rstrip().upper().endswith("BUY"):
        tone = "#6fbf8a"
    elif "→ SELL" in s.upper() or (s.rstrip().upper().endswith("SELL") and "BUY" not in u):
        tone = "#c97a72"
    elif rest.startswith("+") or " +" in rest or ("(+" in rest):
        if "SELL" not in u:
            tone = "#6fbf8a"
    elif rest.startswith(("-", "−")) or " −" in rest:
        if "BUY" not in u:
            tone = "#c97a72"
    if lab:
        return f"[#555555]{lab:14}[/] [{tone}]{rest}[/]"
    # Consensus e.g. "35B · 2H · 0S → BUY"
    if "→" in s:
        left, _, right = s.partition("→")
        right = right.strip()
        r_tone = (
            "#6fbf8a"
            if "BUY" in right.upper()
            else ("#c97a72" if "SELL" in right.upper() else "#e8e8e8")
        )
        return f"[#c8c8c8]{left.strip()}[/] → [{r_tone}]{right}[/]"
    return f"[{tone}]{s}[/]"


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

    /* Earnings — full width (cockpit; no secondary presence stubs) */
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
        width: 1fr;
        margin-right: 0;
        margin-bottom: 0;
    }

    /* Secondary presence map is design-rejected thin stubs — never painted */
    TickerDesk .td-secondary-panel {
        display: none;
        width: 0;
        height: 0;
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

    /* Detail density: OpenCode #tickerDepthBody / .cli-stack (cockpit mock) */
    TickerDesk #td-more-sec {
        height: auto;
        margin: 0 0 1 0;
        padding: 0;
        background: transparent;
        border: none;
    }

    TickerDesk #td-depth-stack {
        height: auto;
        width: 100%;
    }

    /* .cli-panel — elevated card · brass title bar · no dump wall */
    TickerDesk .td-depth-panel {
        background: #141414;
        border: solid #1c1c1c;
        padding: 0;
        margin: 0 0 1 0;
        height: auto;
    }

    TickerDesk .td-depth-title {
        color: #c9a68a;
        text-style: bold;
        background: #121212;
        border-bottom: solid #1c1c1c;
        padding: 0 1;
        height: auto;
    }

    TickerDesk .td-depth-body {
        color: #c8c8c8;
        padding: 0 1 1 1;
        height: auto;
    }

    /* Legacy dump slot — always hidden; detail is card stack only */
    TickerDesk #td-more-body {
        display: none;
        height: 0;
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

    /* Dist dual heat — design: two columns mint | coral (off until job=dist) */
    TickerDesk #td-dist-dual {
        display: none;
    }

    TickerDesk .td-dist-dual {
        height: auto;
        margin-top: 0;
        margin-bottom: 0;
    }

    TickerDesk .td-dist-col {
        width: 1fr;
        height: auto;
        background: #101010;
        border: solid #1c1c1c;
        padding: 0 1 1 1;
        margin-right: 1;
    }

    TickerDesk .td-dist-col.buy {
        border-left: solid #6fbf8a;
    }

    TickerDesk .td-dist-col.sell {
        border-left: solid #c97a72;
        margin-right: 0;
    }

    TickerDesk .td-dist-col-head {
        color: #6b6b6b;
        text-style: bold;
        height: auto;
        margin-bottom: 0;
    }

    TickerDesk .td-dist-col-body {
        color: #a0a0a0;
        height: auto;
    }

    /* Fin three cards — income | balance | cashflow */
    TickerDesk #td-fin-trio {
        display: none;
    }

    TickerDesk .td-fin-trio {
        height: auto;
        margin-top: 0;
    }

    TickerDesk .td-fin-card {
        width: 1fr;
        height: auto;
        background: #101010;
        border: solid #1c1c1c;
        border-left: solid #7aa2c4;
        padding: 0 1 1 1;
        margin-right: 1;
    }

    TickerDesk .td-fin-card.balance {
        border-left: solid #a89cc9;
    }

    TickerDesk .td-fin-card.cashflow {
        border-left: solid #6fbf8a;
        margin-right: 0;
    }

    TickerDesk .td-fin-card-head {
        color: #6b6b6b;
        text-style: bold;
        height: auto;
    }

    TickerDesk .td-fin-card-body {
        color: #a0a0a0;
        height: auto;
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
            TickerFlowDeskModel
            | TickerForeignDeskModel
            | TickerDistDeskModel
            | TickerBrokersDeskModel
            | TickerFinDeskModel
            | None
        ) = None

    def on_mount(self) -> None:
        # Fin sub-chip must not paint until [n] fin is selected (design lock)
        self._sync_fin_period_chip(armed=False)

    def compose(self) -> ComposeResult:
        yield Static("", classes="td-crumb", id="td-crumb")

        # Chip bar: jobs + density. [y] period is fin-context only (hidden until fin is-on).
        yield ChipBar(
            id="td-flags",
            chips=TICKER_JOB_CHIPS,
            chip_id_prefix="td-flag",
            include_fin_period=True,
            period_id="td-flag-period",
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
                # Dist dual heat (hidden unless job=dist)
                with Horizontal(classes="td-dist-dual", id="td-dist-dual"):
                    with Vertical(classes="td-dist-col buy", id="td-dist-buy"):
                        yield Static(
                            "TOP BUYERS · BOUGHT FROM →",
                            classes="td-dist-col-head",
                            id="td-dist-buy-head",
                        )
                        yield Static("", classes="td-dist-col-body", id="td-dist-buy-body")
                    with Vertical(classes="td-dist-col sell", id="td-dist-sell"):
                        yield Static(
                            "TOP SELLERS · SOLD TO →",
                            classes="td-dist-col-head",
                            id="td-dist-sell-head",
                        )
                        yield Static("", classes="td-dist-col-body", id="td-dist-sell-body")
                # Fin three cards (hidden unless job=fin)
                with Horizontal(classes="td-fin-trio", id="td-fin-trio"):
                    for kind, title in (
                        ("income", "INCOME"),
                        ("balance", "BALANCE"),
                        ("cashflow", "CASHFLOW"),
                    ):
                        with Vertical(
                            classes=f"td-fin-card {kind}",
                            id=f"td-fin-{kind}",
                        ):
                            yield Static(
                                title,
                                classes="td-fin-card-head",
                                id=f"td-fin-{kind}-head",
                            )
                            yield Static(
                                "",
                                classes="td-fin-card-body",
                                id=f"td-fin-{kind}-body",
                            )
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
            # Mounted for id stability / tests — never painted (cockpit reject stubs)
            with Vertical(classes="td-section td-secondary-panel", id="td-secondary-sec"):
                yield Static(
                    "SECONDARY · LOCAL PANELS",
                    classes="td-sec-head",
                    id="td-secondary-head",
                )
                yield Static("", classes="td-secondary", id="td-secondary-body")

        # Detail (`d`): OpenCode panel stack — cockpit #tickerDepthBody / .cli-stack
        # No density-restating section head; cards only when detail is-on.
        with Vertical(id="td-more-sec"):
            with Vertical(id="td-depth-stack"):
                for key in _TICKER_PANEL_FLAGS:
                    with Vertical(classes="td-depth-panel", id=f"td-depth-{key}"):
                        yield Static("", id=f"td-depth-t-{key}", classes="td-depth-title")
                        yield Static("", id=f"td-depth-b-{key}", classes="td-depth-body")
            # Legacy dump slot — never shown (reject CLI Rich paste as product surface)
            yield Static("", id="td-more-body")
            # Hidden head kept for scrapers that still query id
            yield Static("", classes="td-sec-head", id="td-more-head")

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
        if key == "period":
            # Binary toggle [y] · quarterly ↔ annual · only armed on fin
            try:
                app = self.app
            except Exception:
                return
            if hasattr(app, "action_toggle_fin_period"):
                app.action_toggle_fin_period()  # type: ignore[attr-defined]
            return
        if self._model is None:
            return
        if key != "detail":
            return
        # Density only on show body — job surfaces are not density stages
        if self._active_job:
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
        desk: (
            TickerFlowDeskModel
            | TickerForeignDeskModel
            | TickerDistDeskModel
            | TickerBrokersDeskModel
            | TickerFinDeskModel
            | None
        ) = None,
    ) -> None:
        """Show/hide job body under chip bar (browse-only CLI sibling).

        Pending load (job set, empty body, no desk): chip ``is-on`` only and
        **hold show panels** until structured ``desk`` arrives — no plain-text
        “Loading…” dump (quiet in-place load contract).
        """
        self._active_job = job
        self._job_title = title or ""
        self._job_body = body or ""
        # Never keep a previous job's structured desk under a different chip
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
        job_ready = bool(self._job_body or self._job_desk is not None)
        if self._active_job:
            load_bit = "" if job_ready else " · loading"
            self.query_one("#td-crumb", Static).update(
                f"View · ticker · [bold #e8e8e8]{model.ticker}[/]   "
                f"[#555555]{self._active_job}{load_bit} · local cache · browse[/]"
            )
        else:
            self.query_one("#td-crumb", Static).update(
                f"View · ticker · [bold #e8e8e8]{model.ticker}[/]   "
                f"[#555555]local cache · browse[/]"
            )
        # Pending job (chip is-on, no payload yet): hold show · no plain-text dump
        job_mode = bool(self._active_job and job_ready)
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
            # Strip density affordance from job footers (show-only control)
            foot = (
                foot.replace(" · d detail", "").replace("d detail · ", "").replace("d detail", "")
            )
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

        # Secondary presence inventory is design-rejected (thin stubs). Never paint.
        try:
            sec = self.query_one("#td-secondary-sec", Vertical)
            sec.display = False
            self.query_one("#td-secondary-head", Static).update("")
            self.query_one("#td-secondary-body", Static).update("")
        except Exception:
            pass

        # Detail = OpenCode cli-stack cards (cockpit #tickerDepthBody), not CLI dump.
        # One elevated card per FULL_PANEL_ORDER remainder · full facts · honest empty.
        # No density-restating section head — state is [d] detail chip is-on only.
        depth_open = self._detail_all or bool(open_flags)
        more_sec = self.query_one("#td-more-sec", Vertical)
        try:
            more_body = self.query_one("#td-more-body", Static)
            more_body.display = False
            more_body.update("")
        except Exception:
            pass
        try:
            head = self.query_one("#td-more-head", Static)
            head.display = False
            head.update("")
        except Exception:
            pass
        by_panel = {p.key: p for p in model.detail_panels}
        if depth_open:
            more_sec.display = True
            for key in _TICKER_PANEL_FLAGS:
                panel_el = self.query_one(f"#td-depth-{key}", Vertical)
                p = by_panel.get(key)
                panel_el.display = True
                title = (p.title if p else key.replace("_", " ")).upper()
                self.query_one(f"#td-depth-t-{key}", Static).update(title)
                body_el = self.query_one(f"#td-depth-b-{key}", Static)
                if p is None or p.status == "missing" or not p.lines:
                    hint = (
                        (p.lines[0] if p and p.lines else "not cached")
                        if p is not None
                        else "not cached"
                    )
                    # Honest empty-slot (cockpit .empty-slot) — never invent facts
                    body_el.update(f"[#555555]{hint}[/]")
                    continue
                body_el.update(
                    "\n".join(line for ln in p.lines if ln and (line := _paint_depth_fact_line(ln)))
                )
        else:
            # Brief default: mast / pulse / earnings only — depth stack closed
            more_sec.display = False
            for key in _TICKER_PANEL_FLAGS:
                try:
                    self.query_one(f"#td-depth-{key}", Vertical).display = False
                except Exception:
                    pass

        self._paint_chip_bar()

        # Footer: fixed word "detail" (chip is-on teaches state — never flip to "brief")
        foot = model.footer or ""
        foot = foot.replace("d collapse", "d detail").replace("d brief", "d detail")
        if "d detail" not in foot and "b f o x n" not in foot:
            # Density only on show; jobs omit d (not contextual)
            if self._active_job == "fin":
                foot = f"b f o x n jobs · y period · {foot}".strip(" ·")
            elif self._active_job:
                foot = f"b f o x n jobs · {foot}".strip(" ·")
            else:
                foot = f"b f o x n jobs · d detail · {foot}".strip(" ·")
        self.query_one("#td-footer", Static).update(
            f"[#555555]{foot}[/]\n[#d4b06a]{model.authority}[/]"
        )

    def _fin_period_grain(self) -> str:
        """CLI-parity grain from app · quarterly (default) | annual."""
        fin_period = "quarterly"
        try:
            fin_period = (
                str(getattr(self.app, "_ticker_fin_period", "quarterly") or "quarterly")
                .strip()
                .lower()
            )
        except Exception:
            pass
        if fin_period not in {"quarterly", "annual"}:
            return "quarterly"
        return fin_period

    def _sync_fin_period_chip(self, *, armed: bool | None = None) -> None:
        """Arm/disarm [y] period — painted only while fin job is front.

        Design: hide (is-context-off), never dim-on-bar for show/other jobs.
        """
        fin_front = self._active_job == "fin" if armed is None else bool(armed)
        grain = self._fin_period_grain()
        period_word = "annual" if grain == "annual" else "quarterly"
        try:
            period = self.query_one("#td-flag-period", FlagChip)
        except Exception:
            return
        if not fin_front:
            period.set_context_visible(False)
            return
        period.set_word(period_word)
        period.set_context_visible(True)
        period.set_chip_state(
            available=True,
            expanded=(grain == "annual"),
        )

    def _sync_detail_chip(self) -> None:
        """Arm/disarm [d] detail — painted only on ticker **show** body.

        Job surfaces (brokers/flow/foreign/dist/fin) are not density stages;
        density would expand show panels that are not mounted under a job.
        """
        try:
            detail = self.query_one("#td-flag-detail", FlagChip)
        except Exception:
            return
        if self._active_job:
            detail.set_context_visible(False)
            return
        detail.set_context_visible(True)
        detail.set_chip_state(available=True, expanded=bool(self._detail_all))

    def _paint_chip_bar(self) -> None:
        on_keys: set[str] = set()
        if self._detail_all and not self._active_job:
            on_keys.add("detail")
        if self._active_job:
            on_keys.add(self._active_job)

        # Fin period grain: **only in fin job context** (not dim-on-bar for other jobs).
        fin_front = self._active_job == "fin"
        if fin_front and self._fin_period_grain() == "annual":
            on_keys.add("period")

        try:
            bar = self.query_one("#td-flags", ChipBar)
            # period + detail are context-scoped — not dim ghosts on wrong surface
            skip: set[str] = {"period"}
            if self._active_job:
                skip.add("detail")
            bar.paint_states(on_keys=on_keys, skip_keys=skip)
            self._sync_fin_period_chip(armed=fin_front)
            self._sync_detail_chip()
        except Exception:
            try:
                self._sync_detail_chip()
            except Exception:
                pass
            try:
                self._sync_fin_period_chip(armed=self._active_job == "fin")
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
        brokers_ok = (
            isinstance(self._job_desk, TickerBrokersDeskModel) and self._active_job == "brokers"
        )
        fin_ok = isinstance(self._job_desk, TickerFinDeskModel) and self._active_job == "fin"

        if flow_ok or foreign_ok or dist_ok or brokers_ok or fin_ok:
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
            elif dist_ok:
                assert isinstance(self._job_desk, TickerDistDeskModel)
                self._paint_dist_desk(self._job_desk)
            elif brokers_ok:
                assert isinstance(self._job_desk, TickerBrokersDeskModel)
                self._paint_brokers_desk(self._job_desk)
            else:
                assert isinstance(self._job_desk, TickerFinDeskModel)
                self._paint_fin_desk(self._job_desk)
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
        desk: (
            TickerFlowDeskModel
            | TickerForeignDeskModel
            | TickerDistDeskModel
            | TickerBrokersDeskModel
            | TickerFinDeskModel
        ),
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

    def _set_job_body_mode(self, mode: str) -> None:
        """Toggle job body chrome: days | dist | fin (mutually exclusive)."""
        show_days = mode == "days"
        show_dist = mode == "dist"
        show_fin = mode == "fin"
        try:
            self.query_one("#td-dist-dual", Horizontal).display = show_dist
        except Exception:
            pass
        try:
            self.query_one("#td-fin-trio", Horizontal).display = show_fin
        except Exception:
            pass
        try:
            self.query_one("#td-flow-days-head", Static).display = show_days
            self.query_one("#td-flow-days", Static).display = show_days
        except Exception:
            pass

    def _set_dist_dual_visible(self, visible: bool) -> None:
        """Compat: dist dual on → hide days/fin."""
        self._set_job_body_mode("dist" if visible else "days")

    def _paint_flow_desk(self, desk: TickerFlowDeskModel) -> None:
        """Design lock: sessions · of-max bar + % · Net · Ratio · desks.

        Scalar bar contract: bar width and % label are the same of-max number.
        Ratio is foreign-flow ratio — not the bar label.
        """
        from src.adapters.tui.board_cell_markup import (
            format_of_max_pct_markup,
            format_scalar_bar_markup,
        )

        self._set_job_body_mode("days")
        self._paint_job_hero_pulses(desk)

        if desk.empty or not desk.days:
            self.query_one("#td-flow-days-head", Static).update("SESSIONS")
            self.query_one("#td-flow-days", Static).update(
                f"[#555555]no sessions · {desk.fetch_hint}[/]"
            )
            return

        n = len(desk.days)
        self.query_one("#td-flow-days-head", Static).update(
            f"SESSIONS · {n} · of max |net| in window · NEWEST FIRST"
        )
        mute = "#555555"
        bar_w = 10
        head = (
            f"[{mute}]{'Date':10}[/]  "
            f"[{mute}]{'':{bar_w}}[/] "
            f"[{mute}]{'%':>4}[/]  "
            f"[{mute}]{'Net':>10}[/]  "
            f"[{mute}]{'Ratio':>7}[/]  "
            f"[{mute}]{'Buyer':>6}[/]  "
            f"[{mute}]{'Seller':>6}[/]"
        )
        lines = [head]
        for d in desk.days:
            tone = {"pos": "#6fbf8a", "neg": "#c97a72"}.get(d.net_tone, "#a0a0a0")
            bar_s = format_scalar_bar_markup(d.bar_pct, width=bar_w, tone=tone)
            pct_s = format_of_max_pct_markup(d.bar_pct, width=4)
            lines.append(
                f"[#d8d8d8]{d.date_s:10}[/]  "
                f"{bar_s} {pct_s}  "
                f"[{tone}]{d.net_s:>10}[/]  "
                f"[#7a7a7a]{d.ratio_s:>7}[/]  "
                f"[#c8c8c8]{d.buyer:>6}[/]  "
                f"[#c8c8c8]{d.seller:>6}[/]"
            )
        self.query_one("#td-flow-days", Static).update("\n".join(lines))

    def _paint_foreign_desk(self, desk: TickerForeignDeskModel) -> None:
        """Design lock: daily points · of-max bar + % · Source · Net · Lot · Avg.

        Scalar bar contract: never solid blocks without a clear of-max % label.
        """
        from src.adapters.tui.board_cell_markup import (
            format_of_max_pct_markup,
            format_scalar_bar_markup,
        )

        self._set_job_body_mode("days")
        self._paint_job_hero_pulses(desk)

        if desk.empty or not desk.days:
            self.query_one("#td-flow-days-head", Static).update("DAILY POINTS")
            self.query_one("#td-flow-days", Static).update(
                f"[#555555]no points · {desk.fetch_hint}[/]"
            )
            return

        n = len(desk.days)
        self.query_one("#td-flow-days-head", Static).update(
            f"DAILY POINTS · {n} · of max |net| in window · NEWEST FIRST"
        )
        mute = "#555555"
        bar_w = 8
        head = (
            f"[{mute}]{'Date':10}[/]  "
            f"[{mute}]{'':{bar_w}}[/] "
            f"[{mute}]{'%':>4}[/]  "
            f"[{mute}]{'Source':10}[/]  "
            f"[{mute}]{'Net':>10}[/]  "
            f"[{mute}]{'Lot':>10}[/]  "
            f"[{mute}]{'Avg':>8}[/]"
        )
        lines = [head]
        for d in desk.days:
            tone = {"pos": "#6fbf8a", "neg": "#c97a72"}.get(d.net_tone, "#a0a0a0")
            bar_s = format_scalar_bar_markup(d.bar_pct, width=bar_w, tone=tone)
            pct_s = format_of_max_pct_markup(d.bar_pct, width=4)
            lines.append(
                f"[#d8d8d8]{d.date_s:10}[/]  "
                f"{bar_s} {pct_s}  "
                f"[#7a7a7a]{d.source:10}[/]  "
                f"[{tone}]{d.net_s:>10}[/]  "
                f"[#c8c8c8]{d.lot_s:>10}[/]  "
                f"[#c8c8c8]{d.avg_s:>8}[/]"
            )
        self.query_one("#td-flow-days", Static).update("\n".join(lines))

    def _paint_dist_desk(self, desk: TickerDistDeskModel) -> None:
        """Design lock: hero · pulses · true dual-column heat · F/L pills · horizontal CP bars."""
        self._set_job_body_mode("dist")
        self._paint_job_hero_pulses(desk)

        mint = "#6fbf8a"
        coral = "#c97a72"
        track_w = 14

        def _pill(tag: str) -> str:
            # Round-ish type badge · F Foreign · L Local · G gov — never A
            c = {"F": "#7aa2c4", "L": "#8a8a8a", "G": "#d4b06a"}.get(tag, "#8a8a8a")
            return f"([{c}]{tag}[/])"

        def _side_text(
            sides: tuple[DistSideRow, ...],
            *,
            arrow: str,
            head_color: str,
            empty_hint: str,
        ) -> str:
            if not sides:
                return f"[#555555]{empty_hint}[/]"
            lines: list[str] = []
            for s in sides:
                # Side header: rank · code · pill · amount (right-ish)
                lines.append(
                    f"[#6b6b6b]{s.rank}[/] [bold #e8e8e8]{s.code}[/] {_pill(s.type_tag)}  "
                    f"[{head_color}]{s.amount_s}[/]"
                )
                for cp in s.cps:
                    # CP row: arrow · code · pill · amount · %
                    lines.append(
                        f"  [#555555]{arrow}[/] [#c8c8c8]{cp.code}[/] {_pill(cp.type_tag)}  "
                        f"[#a0a0a0]{cp.amount_s}[/]  [#6b6b6b]{cp.pct}%[/]"
                    )
                    # Horizontal share track under CP (design heat bar — not a side tower)
                    bar = bar_glyphs(cp.bar_pct, width=track_w, hollow=True)
                    if bar:
                        lines.append(f"    [{head_color}]{bar}[/]")
                    else:
                        lines.append(f"    [#2a2a2a]{'░' * track_w}[/]")
                lines.append("")  # space between sides
            return "\n".join(lines).rstrip()

        try:
            self.query_one("#td-dist-buy-head", Static).update(
                f"[{mint}]TOP BUYERS · BOUGHT FROM →[/]"
            )
            self.query_one("#td-dist-sell-head", Static).update(
                f"[{coral}]TOP SELLERS · SOLD TO →[/]"
            )
            if desk.empty and not desk.buyers and not desk.sellers:
                hint = f"[#555555]no distribution · {desk.fetch_hint}[/]"
                self.query_one("#td-dist-buy-body", Static).update(hint)
                self.query_one("#td-dist-sell-body", Static).update(hint)
            else:
                self.query_one("#td-dist-buy-body", Static).update(
                    _side_text(
                        desk.buyers,
                        arrow="←",
                        head_color=mint,
                        empty_hint="— no buy sides",
                    )
                )
                self.query_one("#td-dist-sell-body", Static).update(
                    _side_text(
                        desk.sellers,
                        arrow="→",
                        head_color=coral,
                        empty_hint="— no sell sides",
                    )
                )
        except Exception:
            # Fallback: keep dual mounted; never invent sides
            pass

    def _paint_brokers_desk(self, desk: TickerBrokersDeskModel) -> None:
        """On-ticker stock desks radar · design cockpit dense table parity.

        Columns: Code · Type · Role · DayNet · Net3/5/7/10/20 · Stk · Δ1
        Type words Foreign/Local · Role buy/sell · mint/coral signed nets.
        """
        from src.adapters.tui.board_cell_markup import format_signed_flow_markup

        self._set_job_body_mode("days")
        self._paint_job_hero_pulses(desk)

        if desk.empty or not desk.rows:
            self.query_one("#td-flow-days-head", Static).update("STOCK DESKS")
            self.query_one("#td-flow-days", Static).update(
                f"[#555555]no top desks · {desk.fetch_hint}[/]"
            )
            return

        n = len(desk.rows)
        self.query_one("#td-flow-days-head", Static).update(
            f"RADAR · {n} · DayNet · Net3/5/7/10/20"
        )
        # Design cockpit headers (not compact Day/N3/R/St)
        mute = "#555555"
        head = (
            f"[{mute}]{'':1}{'Code':4}[/] "
            f"[{mute}]{'Type':7}[/] "
            f"[{mute}]{'Role':4}[/] "
            f"[{mute}]{'DayNet':>8}[/] "
            f"[{mute}]{'Net3':>8}[/] [{mute}]{'Net5':>8}[/] [{mute}]{'Net7':>8}[/] "
            f"[{mute}]{'Net10':>8}[/] [{mute}]{'Net20':>8}[/] "
            f"[{mute}]{'Stk':>3}[/] [{mute}]{'Δ1':>8}[/]"
        )
        lines = [head]
        sel = int(desk.selected_index or 0)
        for i, r in enumerate(desk.rows):
            mark = "[#c9a68a]›[/]" if i == sel else " "
            # Type: dim words (Foreign/Local) — design .dim, not F/L cryptic
            type_s = (r.type_label or "—")[:7]
            type_c = "#7a7a7a"
            role_raw = (r.role or "—").strip().lower()
            if role_raw.startswith("buy"):
                role_s, role_c = "buy", "#6fbf8a"
            elif role_raw.startswith("sell"):
                role_s, role_c = "sell", "#c97a72"
            else:
                role_s, role_c = (r.role or "—")[:4], "#7a7a7a"
            partial = "[#d4b06a]*[/]" if r.has_partial else ""
            lines.append(
                f"{mark}[bold #e8e8e8]{r.code:4}[/] "
                f"[{type_c}]{type_s:7}[/] "
                f"[{role_c}]{role_s:4}[/] "
                f"{format_signed_flow_markup(r.day_net, width=8)} "
                f"{format_signed_flow_markup(r.net3, width=8)} "
                f"{format_signed_flow_markup(r.net5, width=8)} "
                f"{format_signed_flow_markup(r.net7, width=8)} "
                f"{format_signed_flow_markup(r.net10, width=8)} "
                f"{format_signed_flow_markup(r.net20, width=8)} "
                f"[#7a7a7a]{r.streak:>3}[/] "
                f"{format_signed_flow_markup(r.delta1, width=8)}{partial}"
            )
        self.query_one("#td-flow-days", Static).update("\n".join(lines))

    def _paint_fin_desk(self, desk: TickerFinDeskModel) -> None:
        """Design lock: FINANCIALS hero · three cards Income / Balance / Cashflow."""
        self._set_job_body_mode("fin")
        self._paint_job_hero_pulses(desk)

        for card in desk.cards:
            kind = card.kind
            head = self.query_one(f"#td-fin-{kind}-head", Static)
            body = self.query_one(f"#td-fin-{kind}-body", Static)
            if card.status == "ok":
                head.update(f"[#d8d8d8]{card.title}[/]  [#555555]{card.period_label}[/]")
                lines = [f"[#555555]{m.label:8}[/] [#e8e8e8]{m.value}[/]" for m in card.rows]
                for h in card.history:
                    lines.append(f"[#6b6b6b]{h}[/]")
                body.update("\n".join(lines) if lines else "[#555555]—[/]")
            else:
                head.update(f"[#555555]{card.title}[/]")
                body.update(f"[#555555]{card.empty_hint or 'not cached'}[/]")

    def _paint_job_and_chips_only(self) -> None:
        """When model not yet painted, still show ready job body + chips.

        Pending (job without body/desk): chips only — hold show panels.
        """
        try:
            job_sec = self.query_one("#td-job-sec", Vertical)
            ready = bool(self._job_body or self._job_desk is not None)
            if self._active_job and ready:
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
