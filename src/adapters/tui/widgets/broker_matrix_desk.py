"""Broker top-5 multi-window net-buy matrix widget.

Present-only. Design: tui-cockpit-opencode m hub · default 1s emphasis.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static

from src.adapters.tui.broker_desk_matrix_model import (
    DEFAULT_MATRIX_LIMIT,
    DEFAULT_MATRIX_WINDOWS,
    BrokerDeskMatrixModel,
)
from src.adapters.tui.theme import OC, bake_css


class MatrixCell(Static):
    """Clickable matrix cell → view ticker (browse)."""

    can_focus = True

    class Selected(Message):
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker
            super().__init__()

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__("", id=id, classes=classes)
        self.ticker: str | None = None

    def on_click(self) -> None:
        self._activate()

    def on_key(self, event: events.Key) -> None:
        if event.key in {"enter", "space"}:
            event.stop()
            event.prevent_default()
            self._activate()

    def _activate(self) -> None:
        if self.ticker:
            self.post_message(self.Selected(self.ticker))


class BrokerMatrixDesk(Vertical):
    """Multi-window top-5 matrix mounted in stage-scroll."""

    DEFAULT_CSS = bake_css("""
    BrokerMatrixDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: $oc_bg;
    }

    BrokerMatrixDesk .mx-title {
        text-style: bold;
        color: $oc_text_bright;
    }

    BrokerMatrixDesk .mx-sub {
        color: $oc_dim;
        margin-bottom: 0;
    }

    BrokerMatrixDesk .mx-scope {
        color: $oc_purple;
        margin-bottom: 1;
        height: auto;
    }

    BrokerMatrixDesk .mx-grid {
        background: $oc_bg_elevated;
        border: solid $oc_border;
        border-left: solid $oc_peach;
        padding: 0 1 1 1;
        height: auto;
        margin-bottom: 1;
    }

    BrokerMatrixDesk .mx-head-row {
        height: auto;
        margin-bottom: 0;
        border-bottom: solid $oc_border;
        padding-bottom: 0;
    }

    BrokerMatrixDesk .mx-rank-h {
        width: 3;
        color: $oc_dim;
        text-style: bold;
    }

    BrokerMatrixDesk .mx-win-h {
        width: 1fr;
        color: $oc_dim;
        text-align: center;
        text-style: bold;
    }

    BrokerMatrixDesk .mx-win-h.def {
        color: $oc_peach;
        background: $oc_warn_bg;
    }

    BrokerMatrixDesk .mx-row {
        height: auto;
        border-top: solid $oc_border;
        padding-top: 0;
    }

    BrokerMatrixDesk .mx-rank {
        width: 3;
        color: $oc_dim;
        text-style: bold;
    }

    BrokerMatrixDesk .mx-cell {
        width: 1fr;
        height: auto;
        padding: 0 1;
        color: $oc_text;
        border-left: solid $oc_border;
    }

    BrokerMatrixDesk .mx-cell.def {
        background: $oc_warn_bg;
        border-left: solid $oc_peach;
    }

    BrokerMatrixDesk .mx-empty {
        color: $oc_dim;
        height: auto;
        margin: 1 0;
    }

    BrokerMatrixDesk .mx-hub {
        background: $oc_bg_elevated;
        border: solid $oc_border;
        border-left: solid $oc_hairline_strong;
        padding: 0 1;
        height: auto;
        color: $oc_purple;
    }
    """)

    def compose(self) -> ComposeResult:
        yield Static("", id="mx-title", classes="mx-title")
        yield Static("", id="mx-sub", classes="mx-sub")
        yield Static("", id="mx-scope", classes="mx-scope")
        with Vertical(classes="mx-grid", id="mx-grid"):
            with Horizontal(classes="mx-head-row", id="mx-head"):
                yield Static("#", classes="mx-rank-h")
                for i, w in enumerate(DEFAULT_MATRIX_WINDOWS):
                    cls = "mx-win-h def" if w == 1 else "mx-win-h"
                    yield Static(f"{w}s", id=f"mx-wh-{i}", classes=cls)
            for rank in range(DEFAULT_MATRIX_LIMIT):
                with Horizontal(classes="mx-row", id=f"mx-row-{rank}"):
                    yield Static(str(rank + 1), classes="mx-rank")
                    for col in range(len(DEFAULT_MATRIX_WINDOWS)):
                        yield MatrixCell(
                            id=f"mx-c-{rank}-{col}",
                            classes="mx-cell def" if col == 0 else "mx-cell",
                        )
        yield Static("", id="mx-empty", classes="mx-empty")
        yield Static("", id="mx-hub", classes="mx-hub")

    def on_mount(self) -> None:
        self.display = False

    def paint(self, model: BrokerDeskMatrixModel) -> None:
        self.query_one("#mx-title", Static).update(f"Top 5 net buy · {model.broker_code}")
        self.query_one("#mx-sub", Static).update(
            f"{model.broker_name} · {model.type_label} · as of {model.as_of} · "
            f"sessions {model.sessions_cached} · default {model.default_window}s"
        )
        self.query_one("#mx-scope", Static).update(f"{model.scope_note} · net · avg buy · streak")

        # Window headers (support alternate window sets if ever shorter)
        for i, w in enumerate(DEFAULT_MATRIX_WINDOWS):
            h = self.query_one(f"#mx-wh-{i}", Static)
            label = f"{w}s"
            if i < len(model.windows):
                label = f"{model.windows[i]}s"
            h.update(label)
            h.set_class(i < len(model.windows) and model.windows[i] == model.default_window, "def")

        for rank in range(DEFAULT_MATRIX_LIMIT):
            row = model.rows[rank] if rank < len(model.rows) else ()
            for col in range(len(DEFAULT_MATRIX_WINDOWS)):
                slot = self.query_one(f"#mx-c-{rank}-{col}", MatrixCell)
                cell = row[col] if col < len(row) else None
                is_def = col < len(model.windows) and model.windows[col] == model.default_window
                slot.set_class(bool(is_def), "def")
                if cell is None or cell.empty:
                    slot.ticker = None
                    slot.update("[dim]—[/]")
                    continue
                slot.ticker = cell.ticker
                # ticker + streak, net, avg — avg prominent
                tk_color = OC.peach if cell.is_default_window else OC.text_bright
                slot.update(
                    f"[bold {tk_color}]{cell.ticker}[/] [bold {OC.peach}]{cell.streak_label}[/]\n"
                    f"[{OC.mint}]{cell.net_display}[/]\n"
                    f"[bold {OC.text_bright}]{cell.avg_buy_display}[/]"
                )

        empty = self.query_one("#mx-empty", Static)
        if model.empty:
            empty.update(model.empty_reason or "— no net-buy names")
            empty.display = True
        else:
            empty.update("")
            empty.display = False

        self.query_one("#mx-hub", Static).update(model.hub_keys)

    def on_matrix_cell_selected(self, event: MatrixCell.Selected) -> None:
        event.stop()
        ticker = (event.ticker or "").upper()
        if not ticker:
            return
        try:
            app = self.app
            app._focus_ticker = ticker  # type: ignore[attr-defined]
            app._broker_jump_ticker = ticker  # type: ignore[attr-defined]
            if hasattr(app, "action_broker_jump_ticker"):
                app.action_broker_jump_ticker()  # type: ignore[attr-defined]
            elif hasattr(app, "_open_view_ticker_dashboard"):
                app._view_from_desk = True  # type: ignore[attr-defined]
                app._open_view_ticker_dashboard(from_desk=True)  # type: ignore[attr-defined]
        except Exception:
            return
