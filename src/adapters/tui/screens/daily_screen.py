"""Offline Daily workspace backed by one injected application capability.

Layer: Adapter
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from src.adapters.tui.controllers.daily_controller import DailyController
from src.adapters.tui.presenters.daily_presenter import DailyPresenter
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


class DailyScreen(Screen[None]):
    """Render Daily state; all execution occurs in its thread worker."""

    BINDINGS = [
        Binding("r", "reload", "Reload local"),
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

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="daily-shell"):
            yield Static("Daily", id="daily-title")
            yield Static("Idle", id="daily-status")
            with VerticalScroll(id="daily-content"):
                yield Static("", id="daily-clocks", classes="daily-section")
                yield Static("", id="daily-readiness", classes="daily-section")
                yield Static("", id="daily-freshness", classes="daily-section")
                yield Static("", id="daily-regime", classes="daily-section")
                yield Static("", id="daily-opening", classes="daily-section")
                yield Static("", id="daily-accumulation", classes="daily-section")
                yield Static("", id="daily-setup-lens", classes="daily-section")
                yield Static("", id="daily-warnings", classes="daily-section")
        yield Footer()

    def on_mount(self) -> None:
        self.action_reload()

    def action_reload(self) -> None:
        generation = self._controller.begin()
        self._render_state(self._controller.state)
        self._execute_daily(generation)

    @work(thread=True)
    def _execute_daily(self, generation: int) -> None:
        self._controller.execute_generation(
            generation,
            dispatch=self.app.call_from_thread,
            listener=self._render_state,
        )

    def _render_state(self, state: ScreenState) -> None:
        status = self.query_one("#daily-status", Static)
        status.update(state.status.value)
        if state.status is ScreenStatus.LOADING:
            self._clear_sections("Loading local Daily briefing…")
            return
        if state.status is ScreenStatus.ERROR:
            self._clear_sections(
                f"{state.error_type}: {state.error_message}",
                section="#daily-warnings",
            )
            return
        if state.status not in {ScreenStatus.READY, ScreenStatus.EMPTY}:
            return

        view = self._presenter.present(state.payload)
        status.update(f"{state.status.value} — authority {view.overall_authority}")
        self.query_one("#daily-clocks", Static).update("CLOCKS\n" + render_clocks(view))
        self.query_one("#daily-readiness", Static).update("READINESS\n" + render_readiness(view))
        self.query_one("#daily-freshness", Static).update("FRESHNESS\n" + render_freshness(view))
        self.query_one("#daily-regime", Static).update("REGIME\n" + render_regime(view))
        self.query_one("#daily-opening", Static).update("OPENING\n" + render_opening(view))
        self.query_one("#daily-accumulation", Static).update(
            "ACCUMULATION\n" + render_accumulation(view)
        )
        self.query_one("#daily-setup-lens", Static).update("SETUP LENS\n" + render_setup_lens(view))
        self.query_one("#daily-warnings", Static).update("WARNINGS\n" + render_warnings(view))

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
