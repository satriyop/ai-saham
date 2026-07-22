"""Explicit-submit, read-only Research Corpus Health screen.

Layer: Adapter
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

from src.adapters.tui.controllers.research_health_controller import (
    ResearchHealthController,
)
from src.adapters.tui.presenters.research_health_presenter import (
    ResearchHealthPresenter,
)
from src.adapters.tui.state import ScreenState, ScreenStatus
from src.adapters.tui.widgets.research_health import (
    render_cohorts,
    render_counts,
    render_eligibility,
    render_exclusions,
    render_lines,
    render_target,
)


class ResearchHealthScreen(Screen[None]):
    BINDINGS = [
        Binding("enter", "submit", "Run local report"),
        Binding("r", "submit", "Reload local"),
        Binding("escape", "app.show_today", "Back"),
        Binding("?", "app.show_help", "Help"),
    ]

    def __init__(
        self,
        controller: ResearchHealthController,
        presenter: ResearchHealthPresenter,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._presenter = presenter
        self._has_result = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="research-health-shell"):
            yield Static(
                "DIAGNOSTIC ONLY — NOT PROMOTION EVIDENCE",
                id="research-health-banner",
                classes="semantic-warning",
            )
            yield Input(placeholder="Target", id="research-target")
            yield Input(
                placeholder="Semantic compatibility ID (optional)",
                id="research-cohort",
            )
            yield Static("IDLE — enter a target, then submit", id="research-health-status")
            with VerticalScroll(id="research-health-content"):
                yield Static("", id="research-target-result")
                yield Static("", id="research-cohorts")
                yield Static("", id="research-counts")
                yield Static("", id="research-eligibility")
                yield Static("", id="research-blockers")
                yield Static("", id="research-exclusions")
                yield Static("", id="research-notes")
        yield Footer()

    def on_mount(self) -> None:
        self.app.set_route_context("Research")
        self.query_one("#research-target", Input).focus()

    def on_input_submitted(self) -> None:
        self.action_submit()

    def action_submit(self) -> None:
        target = self.query_one("#research-target", Input).value
        cohort_value = self.query_one("#research-cohort", Input).value
        cohort = cohort_value if cohort_value else None
        generation = self._controller.begin()
        self._render_state(self._controller.state)
        self._execute_report(generation, target, cohort)

    @work(thread=True)
    def _execute_report(
        self,
        generation: int,
        target: str,
        cohort: str | None,
    ) -> None:
        self._controller.execute_generation(
            generation,
            target=target,
            cohort=cohort,
            dispatch=self.app.call_from_thread,
            listener=self._render_state,
        )

    def _render_state(self, state: ScreenState) -> None:
        status = self.query_one("#research-health-status", Static)
        if state.status is ScreenStatus.LOADING:
            status.update("LOADING — OFFLINE local readiness report")
            if not self._has_result:
                self._clear_result()
            return
        if state.status is ScreenStatus.ERROR:
            status.update(f"ERROR — {state.error_type}: {state.error_message}")
            return
        if state.status not in {ScreenStatus.READY, ScreenStatus.EMPTY}:
            return
        view = self._presenter.present(state.payload)
        status.update(f"{state.status.value} — report loaded")
        self.query_one("#research-target-result", Static).update("TARGET\n" + render_target(view))
        self.query_one("#research-cohorts", Static).update(
            "SEMANTIC COHORTS\n" + render_cohorts(view)
        )
        self.query_one("#research-counts", Static).update("CORPUS COUNTS\n" + render_counts(view))
        self.query_one("#research-eligibility", Static).update(
            "DIAGNOSTIC / ELIGIBILITY\n" + render_eligibility(view)
        )
        self.query_one("#research-blockers", Static).update(
            "BLOCKERS\n" + render_lines(view.blockers, empty="No blockers.")
        )
        self.query_one("#research-exclusions", Static).update(
            "EXCLUSIONS\n" + render_exclusions(view)
        )
        self.query_one("#research-notes", Static).update(
            "NOTES\n" + render_lines(view.notes, empty="No notes.")
        )
        self._has_result = True

    def _clear_result(self) -> None:
        for selector in (
            "#research-target-result",
            "#research-cohorts",
            "#research-counts",
            "#research-eligibility",
            "#research-blockers",
            "#research-exclusions",
            "#research-notes",
        ):
            self.query_one(selector, Static).update("")
