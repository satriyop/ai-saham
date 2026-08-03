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

    DEFAULT_CSS = """
    BrokerMatrixDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }

    BrokerMatrixDesk .mx-title {
        text-style: bold;
        color: #e8e8e8;
    }

    BrokerMatrixDesk .mx-sub {
        color: #6b6b6b;
        margin-bottom: 0;
    }

    BrokerMatrixDesk .mx-scope {
        color: #9b8fb8;
        margin-bottom: 1;
        height: auto;
    }

    BrokerMatrixDesk .mx-grid {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 0 1 1 1;
        height: auto;
        margin-bottom: 1;
    }

    BrokerMatrixDesk .mx-head-row {
        height: auto;
        margin-bottom: 0;
        border-bottom: solid #1c1c1c;
        padding-bottom: 0;
    }

    BrokerMatrixDesk .mx-rank-h {
        width: 3;
        color: #6b6b6b;
        text-style: bold;
    }

    BrokerMatrixDesk .mx-win-h {
        width: 1fr;
        color: #6b6b6b;
        text-align: center;
        text-style: bold;
    }

    BrokerMatrixDesk .mx-win-h.def {
        color: #c9a68a;
        background: #1a1810;
    }

    BrokerMatrixDesk .mx-row {
        height: auto;
        border-top: solid #1c1c1c;
        padding-top: 0;
    }

    BrokerMatrixDesk .mx-rank {
        width: 3;
        color: #6b6b6b;
        text-style: bold;
    }

    BrokerMatrixDesk .mx-cell {
        width: 1fr;
        height: auto;
        padding: 0 1;
        color: #d8d8d8;
        border-left: solid #1c1c1c;
    }

    BrokerMatrixDesk .mx-cell.def {
        background: #1a1810;
        border-left: solid #c9a68a;
    }

    BrokerMatrixDesk .mx-empty {
        color: #6b6b6b;
        height: auto;
        margin: 1 0;
    }

    BrokerMatrixDesk .mx-hub {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #2a2a2a;
        padding: 0 1;
        height: auto;
        color: #9b8fb8;
    }
    """

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
                tk_color = "#c9a68a" if cell.is_default_window else "#e8e8e8"
                slot.update(
                    f"[bold {tk_color}]{cell.ticker}[/] [bold #c9a68a]{cell.streak_label}[/]\n"
                    f"[#6fbf8a]{cell.net_display}[/]\n"
                    f"[bold #e8e8e8]{cell.avg_buy_display}[/]"
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
