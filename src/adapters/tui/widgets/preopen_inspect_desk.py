"""Pre-open inspect desk — Judge-shaped brief (Act·Risk hero · Why · AUCTION).

Present-only. Design: tui-cockpit-opencode § Pre-open inspect.
No option-chip wall (why / auction+ / plan / warn). Optional [d] detail only.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.shared.trade_action_labels import (
    ACTION_AVOID,
    ACTION_BLOCK,
    ACTION_ENTER,
    ACTION_WATCH,
    AVOID_LIKE,
    ENTER_LIKE,
    WATCH_LIKE,
)
from src.adapters.tui.preopen_inspect_model import PreOpenInspectModel
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
    PreopenInspectDesk .poi-action {
        text-style: bold;
        color: #e8e8e8;
        width: auto;
        padding-right: 2;
    }
    PreopenInspectDesk .poi-action.action-enter { color: #6fbf8a; }
    PreopenInspectDesk .poi-action.action-watch { color: #d4b06a; }
    PreopenInspectDesk .poi-action.action-avoid { color: #c97a72; }
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
        color: #d8d8d8;
    }
    PreopenInspectDesk .poi-sec-title {
        color: #555555;
        text-style: bold;
    }
    PreopenInspectDesk .poi-why {
        color: #7a7a7a;
        height: auto;
        margin-bottom: 1;
    }
    PreopenInspectDesk .poi-panel {
        background: #141414;
        border: solid #1c1c1c;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
        color: #7a7a7a;
    }
    PreopenInspectDesk .poi-warn {
        background: #1a1810;
        border: solid #1a1810;
        color: #d4b06a;
        padding: 0 1;
        margin-bottom: 1;
        height: auto;
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
        self._detail_all: bool = False

    def compose(self) -> ComposeResult:
        yield Static("", id="poi-title", classes="poi-title")
        yield Static("", id="poi-sub", classes="poi-sub")
        with Vertical(classes="poi-hero", id="poi-hero"):
            yield Static("PRE-OPEN · INSPECT", classes="poi-lab", id="poi-lab")
            with Horizontal(id="poi-verdict-row"):
                yield Static("—", id="poi-action", classes="poi-action")
                yield Static("Risk —", id="poi-risk", classes="poi-risk")
            yield Static("", id="poi-present", classes="poi-sub")
            yield Static("", id="poi-iep-hero", classes="poi-sub")
        with Vertical(classes="poi-levels", id="poi-levels"):
            yield Static("LEVELS", classes="poi-sec-title")
            yield Static("", id="poi-levels-body")
        yield Static("", id="poi-why-line", classes="poi-why")
        with Vertical(classes="poi-panel", id="poi-panel-auction"):
            yield Static("AUCTION", classes="poi-sec-title")
            yield Static("", id="poi-auction-body")
        yield Static("", id="poi-warn-banner", classes="poi-warn")
        # Density dual only when model has extra depth — chips painted in paint()
        yield ChipBar(
            id="poi-flags",
            chips=(("detail", "detail · d"),),
            chip_id_prefix="poi-flag",
        )
        with Vertical(classes="poi-panel", id="poi-panel-detail"):
            yield Static("DETAIL", classes="poi-sec-title")
            yield Static("", id="poi-detail-body")
        yield Static("", id="poi-footer", classes="poi-footer")

    def on_mount(self) -> None:
        self.display = False

    def on_flag_chip_selected(self, event: FlagChip.Selected) -> None:
        event.stop()
        if self._model is None:
            return
        if event.flag_key == "detail" and self._model.has_detail:
            self._detail_all = not self._detail_all
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
            self._detail_all = bool(detail_open and model.has_detail)

        self.query_one("#poi-title", Static).update(f"Pre-open · {model.ticker}")
        self.query_one("#poi-sub", Static).update(
            f"#{model.rank}/{model.total}" + (f" · {model.board_meta}" if model.board_meta else "")
        )

        action_el = self.query_one("#poi-action", Static)
        for cls in ("action-enter", "action-watch", "action-avoid"):
            action_el.remove_class(cls)
        act_u = (model.action or "—").upper()
        if act_u in ENTER_LIKE or act_u == ACTION_ENTER:
            action_el.add_class("action-enter")
        elif act_u in WATCH_LIKE or act_u == ACTION_WATCH:
            action_el.add_class("action-watch")
        elif act_u in AVOID_LIKE or act_u == ACTION_AVOID or act_u.startswith("BLOCKED"):
            action_el.add_class("action-avoid")
        action_el.update(f"  {model.action}  ")

        risk_el = self.query_one("#poi-risk", Static)
        risk_el.remove_class("block")
        risk_u = (model.risk or "").upper()
        if model.risk in {"↓"} or risk_u in {ACTION_BLOCK, "BLOCKED", "WARN", "HIGH", "HIGH_RISK"}:
            risk_el.add_class("block")
        risk_el.update(f" risk {model.risk} ")

        self.query_one("#poi-present", Static).update("present-only")
        self.query_one("#poi-iep-hero", Static).update(
            f"IEP  {model.iep}   {model.delta_pct}"
            + ("%" if model.delta_pct not in {"—", "-"} and "%" not in model.delta_pct else "")
        )

        self.query_one("#poi-levels-body", Static).update(
            f"IEV {model.iev} · NCP {model.ncp} · ΔIEV {model.delta_iev}"
            + (f"\n{' · '.join(model.data_lines)}" if model.data_lines else "")
        )

        # Why always visible — never a chip
        self.query_one("#poi-why-line", Static).update(f"[#d4b06a]← Why:[/] {model.why}")

        # AUCTION always on
        auction_panel = self.query_one("#poi-panel-auction", Vertical)
        auction_panel.display = True
        self.query_one("#poi-auction-body", Static).update(
            "\n".join(model.auction_lines) if model.auction_lines else "—"
        )

        # Warn banner only when non-empty
        warn_el = self.query_one("#poi-warn-banner", Static)
        if model.has_warn and model.warn_lines:
            warn_el.display = True
            warn_el.update(" · ".join(model.warn_lines))
        else:
            warn_el.display = False
            warn_el.update("")

        # Density chip only when extra depth exists
        flags_bar = self.query_one("#poi-flags", ChipBar)
        if model.has_detail:
            flags_bar.display = True
            try:
                chip = self.query_one("#poi-flag-detail", FlagChip)
                chip.set_chip_state(
                    available=True,
                    expanded=self._detail_all,
                    warn=False,
                )
            except Exception:
                pass
        else:
            flags_bar.display = False

        detail_panel = self.query_one("#poi-panel-detail", Vertical)
        if self._detail_all and model.has_detail:
            detail_panel.display = True
            body = "\n".join(model.detail_lines) or "\n".join(model.data_lines) or "—"
            self.query_one("#poi-detail-body", Static).update(body)
        else:
            detail_panel.display = False

        foot = model.footer
        if self._detail_all:
            foot = foot.replace("d detail", "d collapse", 1)
        if not model.has_detail:
            foot = foot.replace(" · d detail", "").replace("d detail · ", "")
        self.query_one("#poi-footer", Static).update(foot)
