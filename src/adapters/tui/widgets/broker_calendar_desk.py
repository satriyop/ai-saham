"""Broker desk calendar widget — month grid (mock desk-cal).

Hub ``c``. Present-only browse. Day cells: number · top ticker · net · B/S.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from src.adapters.tui.broker_desk_calendar_model import (
    DOW_LABELS,
    MAX_GRID_CELLS,
    BrokerCalendarCellView,
    BrokerDeskCalendarModel,
    format_calendar_cell_markup,
)

_WEEKS = MAX_GRID_CELLS // 7  # 6


class BrokerCalendarDesk(Vertical):
    """Month calendar density UI — not a monospaced row dump as primary paint."""

    DEFAULT_CSS = """
    BrokerCalendarDesk {
        height: auto;
        width: 100%;
        padding: 0 0 1 0;
        background: #0b0b0b;
    }
    BrokerCalendarDesk .ca-title {
        text-style: bold;
        color: #e8e8e8;
    }
    BrokerCalendarDesk .ca-sub {
        color: #6b6b6b;
        height: auto;
    }
    BrokerCalendarDesk .ca-summary {
        color: #9b8fb8;
        height: auto;
        margin-bottom: 1;
    }
    BrokerCalendarDesk .ca-panel {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #c9a68a;
        padding: 1 1;
        height: auto;
        margin-bottom: 1;
    }
    BrokerCalendarDesk .ca-dow-row {
        height: 1;
        margin-bottom: 0;
        border-bottom: solid #1c1c1c;
        padding-bottom: 0;
    }
    BrokerCalendarDesk .ca-dow {
        width: 1fr;
        color: #6b6b6b;
        text-align: center;
        text-style: bold;
    }
    BrokerCalendarDesk .ca-week {
        height: auto;
        min-height: 5;
    }
    BrokerCalendarDesk .ca-day {
        width: 1fr;
        height: auto;
        min-height: 5;
        padding: 0 1;
        margin: 0 0;
        border: solid #1c1c1c;
        background: #1a1a1a;
        color: #d8d8d8;
    }
    BrokerCalendarDesk .ca-day.pad {
        background: #0b0b0b;
        border: solid #0b0b0b;
    }
    BrokerCalendarDesk .ca-day.blank {
        background: #121212;
        border: solid #161616;
    }
    BrokerCalendarDesk .ca-day.session {
        background: #1a1a1a;
        border: solid #1a1810;
    }
    BrokerCalendarDesk .ca-day.session.pos {
        border: solid #121a14;
        background: #121a14;
    }
    BrokerCalendarDesk .ca-day.session.neg {
        border: solid #1a1212;
        background: #1a1212;
    }
    BrokerCalendarDesk .ca-day.session.asof {
        border: solid #c9a68a;
    }
    BrokerCalendarDesk .ca-day.session.asof.pos,
    BrokerCalendarDesk .ca-day.session.asof.neg {
        border: solid #c9a68a;
    }
    BrokerCalendarDesk .ca-legend {
        color: #6b6b6b;
        height: auto;
        margin: 0 0 1 0;
    }
    BrokerCalendarDesk .ca-empty {
        color: #6b6b6b;
        height: auto;
        margin: 1 0;
    }
    BrokerCalendarDesk .ca-hub {
        background: #141414;
        border: solid #1c1c1c;
        border-left: solid #2a2a2a;
        padding: 0 1;
        height: auto;
        color: #9b8fb8;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="ca-title", classes="ca-title")
        yield Static("", id="ca-sub", classes="ca-sub")
        yield Static("", id="ca-summary", classes="ca-summary")
        with Vertical(classes="ca-panel", id="ca-panel"):
            with Horizontal(classes="ca-dow-row", id="ca-dow-row"):
                for i, lab in enumerate(DOW_LABELS):
                    yield Static(lab, id=f"ca-dow-{i}", classes="ca-dow")
            for week in range(_WEEKS):
                with Horizontal(classes="ca-week", id=f"ca-week-{week}"):
                    for col in range(7):
                        idx = week * 7 + col
                        yield Static(
                            "",
                            id=f"ca-cell-{idx}",
                            classes="ca-day pad",
                        )
        yield Static("", id="ca-legend", classes="ca-legend")
        yield Static("", id="ca-empty", classes="ca-empty")
        yield Static("", id="ca-hub", classes="ca-hub")

    def on_mount(self) -> None:
        self.display = False

    def paint(self, model: BrokerDeskCalendarModel) -> None:
        self.query_one("#ca-title", Static).update(
            f"Calendar · {model.broker_code} · {model.month_label}"
        )
        self.query_one("#ca-sub", Static).update(
            f"{model.broker_name} · {model.type_label} · as of {model.as_of} · "
            f"sessions {model.sessions_cached}"
        )
        self.query_one("#ca-summary", Static).update(f"{model.summary} · {model.scope_note}")

        cells = model.cells
        for idx in range(MAX_GRID_CELLS):
            slot = self.query_one(f"#ca-cell-{idx}", Static)
            cell = cells[idx] if idx < len(cells) else None
            if cell is None:
                slot.update("")
                slot.set_classes("ca-day pad")
                continue
            slot.update(format_calendar_cell_markup(cell))
            slot.set_classes(self._cell_classes(cell))

        self.query_one("#ca-legend", Static).update(model.legend)

        empty = self.query_one("#ca-empty", Static)
        if model.empty:
            empty.update(model.empty_reason or "—")
            empty.display = True
        else:
            empty.update("")
            empty.display = False

        self.query_one("#ca-hub", Static).update(model.hub_keys)

    @staticmethod
    def _cell_classes(cell: BrokerCalendarCellView) -> str:
        parts = ["ca-day", cell.kind]
        if cell.kind == "session":
            if cell.tone in {"pos", "neg", "flat"}:
                parts.append(cell.tone)
            if cell.is_as_of:
                parts.append("asof")
        return " ".join(parts)
