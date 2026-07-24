"""Local-only ticker research detail with isolated preview output.

Layer: Adapter
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from src.adapters.tui.controllers.ticker_research_controller import (
    TickerResearchController,
    TickerUnavailable,
)
from src.adapters.tui.presenters.ticker_research_presenter import TickerResearchPresenter
from src.adapters.tui.state import ScreenState, ScreenStatus
from src.adapters.tui.widgets.research import canonical_verdict, research_section
from src.adapters.tui.worker_lifecycle import dispatch_if_active


class TickerResearchScreen(Screen[None]):
    BINDINGS = [
        Binding("r", "reload", "Refresh"),
        Binding("escape", "app.show_candidates", "Back"),
        Binding("?", "app.show_help", "Help"),
    ]

    def __init__(
        self,
        ticker: str,
        controller: TickerResearchController,
        presenter: TickerResearchPresenter,
    ) -> None:
        super().__init__()
        self._ticker = ticker
        self._controller = controller
        self._presenter = presenter

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="ticker-shell"):
            yield Static(f"{self._ticker} · CANONICAL VERDICT", id="ticker-title")
            yield Static("IDLE", id="ticker-status")
            with VerticalScroll(id="ticker-content"):
                yield Static("", id="ticker-canonical", classes="canonical-verdict")
                yield Static("", id="ticker-evidence")
                yield Static("", id="ticker-diagnostics")
                yield Static("", id="ticker-preview", classes="non-canonical-preview")
                yield Static("", id="ticker-warnings")
        yield Footer()

    def on_mount(self) -> None:
        self.app.set_route_context(f"Candidates / {self._ticker}")
        self.action_reload()

    def action_reload(self) -> None:
        generation = self._controller.begin()
        self._render_state(self._controller.state)
        self._execute_ticker(generation, self._ticker)

    @work(thread=True, exclusive=True)
    def _execute_ticker(self, generation: int, ticker: str) -> None:
        self._controller.execute_generation(
            generation,
            ticker=ticker,
            dispatch=lambda callback, *args: dispatch_if_active(self.app, callback, *args),
            listener=self._render_state,
        )

    def cancel_active_work(self) -> None:
        self.workers.cancel_node(self)
        if self._controller.cancel_current():
            self.query_one("#ticker-status", Static).update(
                "IDLE — local work cancelled; press r to retry"
            )

    def _render_state(self, state: ScreenState) -> None:
        status = self.query_one("#ticker-status", Static)
        status.update(state.status.value)
        if state.status is ScreenStatus.LOADING:
            status.update("LOADING — OFFLINE local swing analysis")
            return
        if state.status is ScreenStatus.UNAVAILABLE:
            unavailable = state.payload
            if not isinstance(unavailable, TickerUnavailable):
                raise TypeError("UNAVAILABLE ticker payload has invalid type")
            status.update(f"UNAVAILABLE — {unavailable.reason}")
            return
        if state.status is ScreenStatus.ERROR:
            status.update(f"ERROR — {state.error_type}: {state.error_message}")
            return
        if state.status is not ScreenStatus.READY:
            return
        view = self._presenter.present(state.payload)
        status.update(f"READY — signal {view.canonical.signal_status}")
        self.query_one("#ticker-canonical", Static).update(
            "CANONICAL VERDICT\n" + canonical_verdict(view)
        )
        self.query_one("#ticker-evidence", Static).update(
            "SUPPORTING EVIDENCE\n" + research_section(view.evidence)
        )
        self.query_one("#ticker-diagnostics", Static).update(
            "DIAGNOSTICS\n" + research_section(view.diagnostics)
        )
        self.query_one("#ticker-preview", Static).update(
            "NON-CANONICAL PREVIEW\n" + research_section(view.preview)
        )
        self.query_one("#ticker-warnings", Static).update(
            "WARNINGS\n" + ("\n".join(view.warnings) if view.warnings else "No warnings.")
        )
