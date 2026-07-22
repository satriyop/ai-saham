"""Modal confirmation dialog for market data refresh operations.

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from src.application.use_case.refresh_daily_workspace_use_case import (
    DailyWorkspaceRefreshPlan,
)


class UpdateConfirmationModal(ModalScreen[bool]):
    """Confirmation modal dialog for market data refresh operations."""

    DEFAULT_CSS = """
    UpdateConfirmationModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #dialog-card {
        width: 64;
        height: auto;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #dialog-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #dialog-disclosure {
        color: $warning;
        margin-top: 1;
        margin-bottom: 1;
    }

    #dialog-buttons {
        height: auto;
        align: right bottom;
        margin-top: 1;
    }

    #confirm-btn {
        margin-right: 2;
    }
    """

    def __init__(self, plan: DailyWorkspaceRefreshPlan) -> None:
        super().__init__()
        self._plan = plan

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog-card"):
            yield Static("CONFIRM MARKET DATA UPDATE", id="dialog-title")
            yield Static(
                f"Universe          : {self._plan.universe.upper()}\n"
                f"Resolved Tickers  : {self._plan.resolved_ticker_count}\n"
                f"History Days      : {self._plan.history_days}\n"
                f"Candles Provider  : {self._plan.candles_provider_label}\n"
                f"Broker Provider   : {self._plan.broker_provider_label}\n"
                f"Components        : {self._plan.components}",
                id="dialog-details",
            )
            yield Static(
                f"[ WRITE ACTION: {self._plan.local_write_disclosure} ]",
                id="dialog-disclosure",
            )
            with Horizontal(id="dialog-buttons"):
                yield Button("Confirm Update", variant="primary", id="confirm-btn")
                yield Button("Cancel", variant="error", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)
