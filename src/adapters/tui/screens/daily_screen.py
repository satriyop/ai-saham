"""Offline Daily command center workspace backed by injected application capabilities.

Layer: Adapter
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, ProgressBar, Static

from src.adapters.tui.controllers.daily_controller import DailyController
from src.adapters.tui.presenters.daily_presenter import DailyPresenter
from src.adapters.tui.screens.update_confirmation_modal import (
    UpdateConfirmationModal,
)
from src.adapters.tui.state import ScreenState, ScreenStatus
from src.adapters.tui.widgets.daily import (
    render_accumulation,
    render_clocks,
    render_freshness,
    render_opening,
    render_readiness,
    render_regime,
    render_setup_lens,
    render_warnings,
)
from src.adapters.tui.worker_lifecycle import dispatch_if_active
from src.application.use_case.refresh_daily_workspace_use_case import (
    RefreshDailyWorkspaceRequest,
)


class DailyScreen(Screen[None]):
    """Render Dashboard command center; execution occurs in thread workers."""

    BINDINGS = [
        Binding("u", "update_data", "Update data"),
        Binding("r", "reload", "Refresh"),
        Binding("?", "app.show_help", "Help"),
        Binding("h", "app.show_help", "Help", show=False),
    ]

    def __init__(
        self,
        controller: DailyController,
        presenter: DailyPresenter,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._presenter = presenter
        self._has_rendered_result = False
        self._active_universe = "lq45"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="daily-shell"):
            yield Static("Daily", id="daily-title")
            with Horizontal(id="daily-action-bar"):
                yield Static(
                    "IDLE — OFFLINE", id="daily-status", classes="semantic-info"
                )
                yield Button("Update Data", id="update-btn", variant="primary")
                yield Button("Refresh", id="reload-btn", variant="default")
            yield ProgressBar(id="daily-progress", show_percentage=True, show_eta=True)
            with VerticalScroll(id="daily-content"):
                yield Static("", id="daily-warnings", classes="daily-section")
                yield Static(
                    "", id="daily-accumulation", classes="daily-section"
                )
                yield Static("", id="daily-regime", classes="daily-section")
                yield Static("", id="daily-readiness", classes="daily-section")
                yield Static("", id="daily-clocks", classes="daily-section")
                yield Static("", id="daily-opening", classes="daily-section")
                yield Static("", id="daily-setup-lens", classes="daily-section")
                yield Static("", id="daily-freshness", classes="daily-section")
        yield Footer()

    def on_mount(self) -> None:
        progress = self.query_one("#daily-progress", ProgressBar)
        progress.display = False
        self.action_reload()

    def action_reload(self) -> None:
        generation = self._controller.begin()
        self._render_state(self._controller.state)
        self._execute_reload(generation)

    def action_update_data(self) -> None:
        req = RefreshDailyWorkspaceRequest(universe=self._active_universe)
        plan = self._controller.get_preview(req)
        if plan is None:
            self.action_reload()
            return

        def handle_confirmation(confirmed: bool | None) -> None:
            if confirmed:
                generation = self._controller.begin()
                self._render_state(self._controller.state)
                self._execute_refresh(generation, req)

        self.app.push_screen(UpdateConfirmationModal(plan), handle_confirmation)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "update-btn":
            self.action_update_data()
        elif event.button.id == "reload-btn":
            self.action_reload()

    @work(thread=True, exclusive=True)
    def _execute_reload(self, generation: int) -> None:
        self._controller.execute_reload_generation(
            generation,
            dispatch=lambda callback, *args: dispatch_if_active(
                self.app, callback, *args
            ),
            listener=self._render_state,
        )

    @work(thread=True, exclusive=True)
    def _execute_refresh(
        self, generation: int, request: RefreshDailyWorkspaceRequest
    ) -> None:
        self._controller.execute_refresh_generation(
            generation,
            request,
            dispatch=lambda callback, *args: dispatch_if_active(
                self.app, callback, *args
            ),
            listener=self._render_state,
            progress_callback=self._handle_progress_event,
        )

    def _handle_progress_event(self, data: dict[str, Any]) -> None:
        progress = self.query_one("#daily-progress", ProgressBar)
        if data.get("type") == "start":
            progress.display = True
            progress.total = data.get("total", 100)
            progress.progress = 0
        elif data.get("type") == "ticker":
            progress.display = True
            progress.progress = data.get("index", 0)

    def cancel_active_work(self) -> None:
        self.workers.cancel_node(self)
        if self._controller.cancel_current():
            self.query_one("#daily-status", Static).update(
                "IDLE — work cancelled; press r to retry"
            )
            progress = self.query_one("#daily-progress", ProgressBar)
            progress.display = False

    def _render_state(self, state: ScreenState) -> None:
        status = self.query_one("#daily-status", Static)
        progress = self.query_one("#daily-progress", ProgressBar)
        status.update(state.status.value)
        if state.status is ScreenStatus.LOADING:
            status.update("RUNNING — Market Data Refresh / Recomputation")
            status.set_classes("semantic-warning")
            if not self._has_rendered_result:
                self._clear_sections("Loading Daily Command Center…")
            return

        progress.display = False
        if state.status is ScreenStatus.ERROR:
            status.update("ERROR — retry with Refresh or Update")
            status.set_classes("semantic-error")
            self._clear_sections(
                f"{state.error_type}: {state.error_message}",
                section="#daily-warnings",
            )
            return

        if state.status not in {ScreenStatus.READY, ScreenStatus.EMPTY}:
            return

        view = self._presenter.present(state.payload)
        self._active_universe = view.universe
        status.update(f"{state.status.value} — authority {view.overall_authority}")
        status.set_classes(self._authority_class(view.overall_authority))
        self.app.set_route_context(
            "Today",
            universe=view.universe,
            as_of=view.clocks[1].value,
        )
        self.query_one("#daily-clocks", Static).update("CLOCKS\n" + render_clocks(view))
        self.query_one("#daily-readiness", Static).update("READINESS\n" + render_readiness(view))
        self.query_one("#daily-freshness", Static).update("FRESHNESS\n" + render_freshness(view))
        self.query_one("#daily-regime", Static).update("REGIME\n" + render_regime(view))
        self.query_one("#daily-opening", Static).update("OPENING\n" + render_opening(view))
        self.query_one("#daily-accumulation", Static).update(
            "TODAY'S CANDIDATES\n" + render_accumulation(view)
        )
        self.query_one("#daily-setup-lens", Static).update("SETUP LENS\n" + render_setup_lens(view))
        self.query_one("#daily-warnings", Static).update("WARNINGS\n" + render_warnings(view))
        self._has_rendered_result = True

    @staticmethod
    def _authority_class(authority: str) -> str:
        return {
            "READY": "semantic-ready",
            "PARTIAL": "semantic-warning",
            "NOT_READY": "semantic-error",
        }.get(authority, "semantic-unavailable")

    def _clear_sections(self, message: str, *, section: str = "#daily-clocks") -> None:
        for selector in (
            "#daily-clocks",
            "#daily-readiness",
            "#daily-freshness",
            "#daily-regime",
            "#daily-opening",
            "#daily-accumulation",
            "#daily-setup-lens",
            "#daily-warnings",
        ):
            self.query_one(selector, Static).update(message if selector == section else "")
