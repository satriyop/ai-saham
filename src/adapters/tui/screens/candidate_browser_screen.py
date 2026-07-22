"""Canonical-order accumulation Candidate Browser.

Layer: Adapter
"""

from __future__ import annotations

from textual import events, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static

from src.adapters.tui.controllers.accumulation_controller import AccumulationController
from src.adapters.tui.presenters.accumulation_presenter import (
    AccumulationPresenter,
    AccumulationViewModel,
)
from src.adapters.tui.state import ScreenState, ScreenStatus
from src.adapters.tui.widgets.research import (
    candidate_label,
    candidate_metadata,
    selected_candidate,
)
from src.adapters.tui.worker_lifecycle import dispatch_if_active


class CandidateBrowserScreen(Screen[None]):
    BINDINGS = [
        Binding("r", "reload", "Reload local"),
        Binding("m", "toggle_multi", "Single/Multi"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("enter", "open_selected", "Open ticker"),
        Binding("escape", "app.show_today", "Back"),
        Binding("?", "app.show_help", "Help"),
    ]

    def __init__(self, controller: AccumulationController, presenter: AccumulationPresenter):
        super().__init__()
        self._controller = controller
        self._presenter = presenter
        self._multi = False
        self._view: AccumulationViewModel | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="candidate-shell"):
            yield Static("CANDIDATES — OFFLINE", id="candidate-title", classes="semantic-info")
            yield Static(
                "Minimum terminal size is 80 columns.",
                id="minimum-size-warning",
            )
            yield Static("IDLE", id="candidate-status")
            yield Static("", id="candidate-metadata")
            with Horizontal(id="candidate-workspace"):
                yield OptionList(id="candidate-list")
                with VerticalScroll(id="candidate-preview"):
                    yield Static("No candidate selected.", id="candidate-selected")
            yield Static("", id="candidate-warnings")
        yield Footer()

    def on_mount(self) -> None:
        self.app.set_route_context("Candidates")
        self.query_one("#candidate-list", OptionList).focus()
        self.action_reload()

    def on_resize(self, event: events.Resize) -> None:
        width = event.size.width
        self.set_class(width < 80, "too-small")
        self.set_class(80 <= width < 100, "compact")
        self.set_class(width >= 120, "wide")

    def action_reload(self) -> None:
        generation = self._controller.begin()
        self._render_state(self._controller.state)
        self._execute_accumulation(generation, self._multi)

    def action_toggle_multi(self) -> None:
        self._multi = not self._multi
        self.action_reload()

    @work(thread=True, exclusive=True)
    def _execute_accumulation(self, generation: int, multi: bool) -> None:
        self._controller.execute_generation(
            generation,
            multi=multi,
            dispatch=lambda callback, *args: dispatch_if_active(self.app, callback, *args),
            listener=self._render_state,
        )

    def cancel_active_work(self) -> None:
        self.workers.cancel_node(self)
        if self._controller.cancel_current():
            self.query_one("#candidate-status", Static).update(
                "IDLE — local work cancelled; press r to retry"
            )

    def action_cursor_down(self) -> None:
        options = self.query_one("#candidate-list", OptionList)
        if options.option_count:
            current = options.highlighted or 0
            options.highlighted = min(current + 1, options.option_count - 1)
            self._render_selected()

    def action_cursor_up(self) -> None:
        options = self.query_one("#candidate-list", OptionList)
        if options.option_count:
            current = options.highlighted or 0
            options.highlighted = max(current - 1, 0)
            self._render_selected()

    def action_open_selected(self) -> None:
        row = self._selected_row()
        if row is not None:
            self.app.action_open_ticker(row.ticker)

    def on_option_list_option_highlighted(self) -> None:
        self._render_selected()

    def on_option_list_option_selected(self) -> None:
        self.action_open_selected()

    def _render_state(self, state: ScreenState) -> None:
        status = self.query_one("#candidate-status", Static)
        status.update(state.status.value)
        if state.status is ScreenStatus.LOADING:
            status.update("LOADING — OFFLINE local accumulation projection")
            return
        if state.status is ScreenStatus.ERROR:
            status.update(f"ERROR — {state.error_type}: {state.error_message}")
            return
        if state.status not in {ScreenStatus.READY, ScreenStatus.EMPTY}:
            return
        view = self._presenter.present(state.payload)
        self._view = view
        status.update(f"{state.status.value} — {'MULTI' if view.multi else 'SINGLE'}")
        self.query_one("#candidate-metadata", Static).update(candidate_metadata(view))
        options = self.query_one("#candidate-list", OptionList)
        options.clear_options()
        options.add_options(candidate_label(index, row) for index, row in enumerate(view.rows))
        if view.rows:
            options.highlighted = 0
        self.query_one("#candidate-warnings", Static).update(
            "WARNINGS\n" + ("\n".join(view.warnings) if view.warnings else "No warnings.")
        )
        self._render_selected()

    def _selected_row(self):
        options = self.query_one("#candidate-list", OptionList)
        if self._view is None or options.highlighted is None:
            return None
        if options.highlighted >= len(self._view.rows):
            return None
        return self._view.rows[options.highlighted]

    def _render_selected(self) -> None:
        self.query_one("#candidate-selected", Static).update(
            selected_candidate(self._selected_row())
        )
