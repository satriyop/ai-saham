"""Pre-open inspect desk — grade hero · levels · flag chips (why / auction+ / warn).

Present-only browse. Design: tui-cockpit-opencode preopenInspectView.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.shared.trade_action_labels import ACTION_BLOCK
from src.adapters.tui.preopen_inspect_model import (
    EXPANDABLE_FLAGS,
    FLAG_DEFS,
    PreOpenInspectModel,
)
from src.adapters.tui.widgets.chip_bar import ChipBar
from src.adapters.tui.widgets.flag_chip import FlagChip


class PreopenInspectDesk(Vertical):
    DEFAULT_CSS = """
    PreopenInspectDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }
    PreopenInspectDesk .poi-title {
        text-style: bold;
        color: #e8e8e8;
    }
    PreopenInspectDesk .poi-sub {
        color: #555555;
        margin-bottom: 1;
        height: auto;
    }
    PreopenInspectDesk .poi-hero {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #d4b06a;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }
    PreopenInspectDesk .poi-lab {
        color: #c9a68a;
        text-style: bold;
    }
    PreopenInspectDesk .poi-grade {
        text-style: bold;
        color: #e8e8e8;
        width: auto;
        padding-right: 2;
    }
    PreopenInspectDesk .poi-risk {
        color: #6fbf8a;
        width: auto;
        padding: 0 1;
        background: #121a14;
    }
    PreopenInspectDesk .poi-risk.block {
        color: #c97a72;
        background: #1a1212;
    }
    PreopenInspectDesk .poi-levels {
        background: #141414;
        border: solid #1c1c1c;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
        color: #c8c8c8;
    }
    PreopenInspectDesk .poi-sec-title {
        color: #555555;
        text-style: bold;
    }
    PreopenInspectDesk .poi-panel {
        background: #141414;
        border: solid #1c1c1c;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
        color: #a0a0a0;
    }
    PreopenInspectDesk .poi-footer {
        color: #555555;
        height: auto;
        margin-top: 0;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self._model: PreOpenInspectModel | None = None
        self._open_flags: set[str] = set()
        self._detail_all: bool = False

    def compose(self) -> ComposeResult:
        yield Static("", id="poi-title", classes="poi-title")
        yield Static("", id="poi-sub", classes="poi-sub")
        with Vertical(classes="poi-hero", id="poi-hero"):
            yield Static("PRE-OPEN · INSPECT", classes="poi-lab", id="poi-lab")
            with Horizontal(id="poi-verdict-row"):
                yield Static("—", id="poi-grade", classes="poi-grade")
                yield Static("Risk —", id="poi-risk", classes="poi-risk")
            yield Static("", id="poi-why-line", classes="poi-sub")
        with Vertical(classes="poi-levels", id="poi-levels"):
            yield Static("LEVELS", classes="poi-sec-title")
            yield Static("", id="poi-levels-body")
        # Option chips only (bible §2) — no density wall / no row label
        yield ChipBar(
            id="poi-flags",
            chips=tuple((k, lab) for k, lab in FLAG_DEFS if k != "detail"),
            chip_id_prefix="poi-flag",
        )
        with Vertical(classes="poi-panel", id="poi-panel-why"):
            yield Static("WHY", classes="poi-sec-title")
            yield Static("", id="poi-why-body")
        with Vertical(classes="poi-panel", id="poi-panel-auction"):
            yield Static("AUCTION+", classes="poi-sec-title")
            yield Static("", id="poi-auction-body")
        with Vertical(classes="poi-panel", id="poi-panel-warn"):
            yield Static("WARN", classes="poi-sec-title")
            yield Static("", id="poi-warn-body")
        with Vertical(classes="poi-panel", id="poi-panel-data"):
            yield Static("DATA", classes="poi-sec-title")
            yield Static("", id="poi-data-body")
        yield Static("", id="poi-footer", classes="poi-footer")

    def on_mount(self) -> None:
        self.display = False

    def on_flag_chip_selected(self, event: FlagChip.Selected) -> None:
        event.stop()
        if self._model is None:
            return
        key = event.flag_key
        if key == "detail":
            self._detail_all = not self._detail_all
            if self._detail_all:
                self._open_flags = set(self._available(self._model))
            else:
                self._open_flags.clear()
        elif key in EXPANDABLE_FLAGS:
            if key not in self._available(self._model):
                return
            if key in self._open_flags:
                self._open_flags.discard(key)
            else:
                self._open_flags.add(key)
            self._detail_all = self._open_flags >= self._available(self._model)
        self.paint(self._model, detail_open=self._detail_all, sync_from_detail=False)
        try:
            app = self.app
            if hasattr(app, "_preopen_detail_open"):
                app._preopen_detail_open = self._detail_all  # type: ignore[attr-defined]
        except Exception:
            pass

    def paint(
        self,
        model: PreOpenInspectModel,
        *,
        detail_open: bool = False,
        sync_from_detail: bool = True,
    ) -> None:
        self._model = model
        if sync_from_detail:
            self._detail_all = detail_open
            if detail_open:
                self._open_flags = set(self._available(model))
            else:
                self._open_flags.clear()
        open_flags = set(self._open_flags)
        if self._detail_all:
            open_flags |= self._available(model)

        self.query_one("#poi-title", Static).update(f"Screen · pre-open · {model.ticker}")
        self.query_one("#poi-sub", Static).update(
            f"#{model.rank}/{model.total}" + (f" · {model.board_meta}" if model.board_meta else "")
        )
        self.query_one("#poi-grade", Static).update(f"  {model.grade}  ")
        risk_el = self.query_one("#poi-risk", Static)
        risk_el.remove_class("block")
        risk_u = (model.risk or "").upper()
        if risk_u in {ACTION_BLOCK, "BLOCKED", "WARN", "HIGH"}:
            risk_el.add_class("block")
        risk_el.update(f" Risk {model.risk} ")
        # Compact why line when why panel closed
        self.query_one("#poi-why-line", Static).update(
            f"[#7a7a7a]Why[/]  {model.why}" if "why" not in open_flags else ""
        )

        self.query_one("#poi-levels-body", Static).update(
            f"IEP {model.iep} · Δ% {model.delta_pct} · IEV {model.iev}\n"
            f"NCP {model.ncp} · ΔIEV {model.delta_iev}"
        )

        by_flag = {c.key: c for c in model.flags}
        for key, _label in FLAG_DEFS:
            if key == "detail":
                continue  # no density chip on pre-open (option chips only)
            chip_m = by_flag.get(key)
            available = bool(chip_m and chip_m.available)
            warn = bool(chip_m and chip_m.warn)
            expanded = key in open_flags
            try:
                self.query_one(f"#poi-flag-{key}", FlagChip).set_chip_state(
                    available=available, expanded=expanded, warn=warn
                )
            except Exception:
                pass

        why_panel = self.query_one("#poi-panel-why", Vertical)
        auction_panel = self.query_one("#poi-panel-auction", Vertical)
        warn_panel = self.query_one("#poi-panel-warn", Vertical)
        data_panel = self.query_one("#poi-panel-data", Vertical)

        if "why" in open_flags:
            why_panel.display = True
            self.query_one("#poi-why-body", Static).update(model.why)
        else:
            why_panel.display = False

        if "auction_plus" in open_flags:
            auction_panel.display = True
            self.query_one("#poi-auction-body", Static).update(
                "\n".join(model.auction_lines) or "—"
            )
        else:
            auction_panel.display = False

        if "warn" in open_flags and model.has_warn:
            warn_panel.display = True
            self.query_one("#poi-warn-body", Static).update(
                "\n".join(model.warn_lines) if model.warn_lines else "—"
            )
        else:
            warn_panel.display = False

        # Data panel with detail-all only (supporting context)
        if self._detail_all:
            data_panel.display = True
            self.query_one("#poi-data-body", Static).update("\n".join(model.data_lines))
        else:
            data_panel.display = False

        foot = model.footer
        if self._detail_all:
            foot = foot.replace("d detail", "d collapse", 1)
        self.query_one("#poi-footer", Static).update(foot)

    def _available(self, model: PreOpenInspectModel) -> set[str]:
        out: set[str] = set()
        for c in model.flags:
            if c.key in EXPANDABLE_FLAGS and c.available:
                out.add(c.key)
        return out
