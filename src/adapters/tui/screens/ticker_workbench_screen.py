"""Ticker Decision Workbench — tabbed decision screen with a persistent strip.

Replaces the narrow single-response ticker drilldown. The canonical verdict and
blockers stay fixed above the tabs after a valid analysis; Overview / Setup /
Signal & Risk only reorganize the already-computed result. Selecting a tab, mode,
or setup never starts work — only an explicit Run does.

Layer: Adapter
"""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Select, Static

from src.adapters.tui.presenters.ticker_workbench_presenter import (
    TickerWorkbenchPresenter,
)
from src.adapters.tui.state import ScreenState, ScreenStatus
from src.adapters.tui.ticker_refresh_mode import TickerRefreshMode
from src.adapters.tui.widgets.workbench import (
    header_line,
    overview_body,
    setup_body,
    signal_risk_body,
    verdict_line,
)
from src.adapters.tui.worker_lifecycle import dispatch_if_active
from src.application.use_case.evaluate_swing_setup_use_case import AVAILABLE_SWING_SETUPS

_NO_SETUP = "(no setup)"
_TABS: tuple[tuple[str, str], ...] = (
    ("overview", "Overview"),
    ("setup", "Setup"),
    ("signal_risk", "Signal & Risk"),
)
_SEVERITY_CLASS: dict[str, str] = {
    "bullish": "semantic-ready",
    "caution": "semantic-warning",
    "bearish": "semantic-error",
    "unavailable": "semantic-unavailable",
    "info": "semantic-info",
}


class TickerWorkbenchScreen(Screen[None]):
    BINDINGS = [
        Binding("r", "run", "Run analysis"),
        Binding("escape", "back", "Back"),
        Binding("?", "app.show_help", "Help"),
    ]

    def __init__(self, ticker, controller, presenter: TickerWorkbenchPresenter) -> None:
        super().__init__()
        self._ticker = ticker
        self._controller = controller
        self._presenter = presenter
        self._mode = TickerRefreshMode.CACHED_ONLY
        self._setup: str | None = None
        self._active_tab = "overview"
        self._view = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="workbench-shell"):
            # Persistent decision strip (fixed above tabs).
            yield Static(f"{self._ticker}  ·  press r to Run", id="wb-header")
            yield Static("VERDICT  — run analysis", id="wb-verdict")
            yield Static("BLOCKERS  —", id="wb-blockers")
            yield Static("IDLE", id="wb-status")
            with Horizontal(id="wb-controls"):
                yield Select(
                    [(m.label, m.name) for m in TickerRefreshMode],
                    value=self._mode.name,
                    allow_blank=False,
                    id="wb-mode",
                )
                yield Select(
                    [(_NO_SETUP, _NO_SETUP)] + [(s, s) for s in AVAILABLE_SWING_SETUPS],
                    value=_NO_SETUP,
                    allow_blank=False,
                    id="wb-setup",
                )
                yield Button("Run", id="wb-run", variant="primary")
            with Horizontal(id="wb-tab-bar"):
                for tab_id, label in _TABS:
                    yield Button(
                        label,
                        id=f"wb-tab-{tab_id}",
                        classes="tab-btn active-tab" if tab_id == "overview" else "tab-btn",
                    )
            with VerticalScroll(id="wb-content"):
                yield Static("Select a mode and setup, then press Run.", id="wb-tab-body")
        yield Footer()

    def on_mount(self) -> None:
        self.app.set_route_context(f"Ticker / {self._ticker}")

    # --- Selection: never triggers work ---------------------------------

    @on(Select.Changed, "#wb-mode")
    def _on_mode(self, event: Select.Changed) -> None:
        self._mode = TickerRefreshMode[str(event.value)]
        self._refresh_header_only()

    @on(Select.Changed, "#wb-setup")
    def _on_setup(self, event: Select.Changed) -> None:
        value = str(event.value)
        self._setup = None if value == _NO_SETUP else value
        self._refresh_header_only()

    @on(Button.Pressed, "#wb-run")
    def _on_run(self, event: Button.Pressed) -> None:
        self.action_run()

    @on(Button.Pressed, ".tab-btn")
    def _on_tab(self, event: Button.Pressed) -> None:
        tab_id = str(event.button.id).removeprefix("wb-tab-")
        self._select_tab(tab_id)

    # --- Explicit actions ------------------------------------------------

    def action_run(self) -> None:
        generation = self._controller.begin()
        self._render_state(self._controller.state)
        self._execute(generation, self._ticker, self._mode, self._setup)

    def action_back(self) -> None:
        self.cancel_active_work()
        self.app.pop_screen()

    @work(thread=True, exclusive=True)
    def _execute(self, generation, ticker, mode, setup) -> None:
        self._controller.execute_generation(
            generation,
            ticker=ticker,
            mode=mode,
            setup=setup,
            dispatch=lambda callback, *args: dispatch_if_active(self.app, callback, *args),
            listener=self._render_state,
        )

    def cancel_active_work(self) -> None:
        self.workers.cancel_node(self)
        if self._controller.cancel_current():
            self.query_one("#wb-status", Static).update(
                "IDLE — analysis cancelled; press r to retry"
            )

    # --- Rendering -------------------------------------------------------

    def _select_tab(self, tab_id: str) -> None:
        self._active_tab = tab_id
        for known_id, _ in _TABS:
            button = self.query_one(f"#wb-tab-{known_id}", Button)
            button.set_class(known_id == tab_id, "active-tab")
        self._render_active_tab()

    def _refresh_header_only(self) -> None:
        if self._view is None:
            self.query_one("#wb-header", Static).update(
                f"{self._ticker}   Mode [{self._mode.label}]   "
                f"Setup [{self._setup or _NO_SETUP}]  ·  press r to Run"
            )

    def _render_state(self, state: ScreenState) -> None:
        status = self.query_one("#wb-status", Static)
        if state.status is ScreenStatus.LOADING:
            status.update(f"LOADING — {self._mode.label} analysis")
            return
        if state.status is ScreenStatus.UNAVAILABLE:
            unavailable = state.payload
            reason = getattr(unavailable, "reason", "unavailable")
            status.update(f"UNAVAILABLE — {reason}")
            self.query_one("#wb-verdict", Static).update("VERDICT  — UNAVAILABLE")
            return
        if state.status is ScreenStatus.ERROR:
            status.update(f"ERROR — {state.error_type}: {state.error_message}")
            return
        if state.status is not ScreenStatus.READY:
            return
        self._view = self._presenter.present(state.payload)
        status.update(f"READY — {self._mode.label}")
        self.query_one("#wb-header", Static).update(
            header_line(self._view.decision, mode_label=self._mode.label)
        )
        verdict_widget = self.query_one("#wb-verdict", Static)
        verdict_widget.update("VERDICT  " + verdict_line(self._view.decision))
        # Severity reinforces the text badge with semantic color; the text/symbol
        # already carries the status, so color is never the only signal.
        severity_class = _SEVERITY_CLASS.get(
            self._view.decision.badge.severity, "semantic-info"
        )
        for known in _SEVERITY_CLASS.values():
            verdict_widget.set_class(known == severity_class, known)
        blockers = self._view.decision.blockers
        self.query_one("#wb-blockers", Static).update(
            "BLOCKERS  " + (", ".join(blockers) if blockers else "none")
        )
        self._render_active_tab()

    def _render_active_tab(self) -> None:
        body = self.query_one("#wb-tab-body", Static)
        if self._view is None:
            body.update("Select a mode and setup, then press Run.")
            return
        renderers = {
            "overview": overview_body,
            "setup": setup_body,
            "signal_risk": signal_risk_body,
        }
        body.update(renderers[self._active_tab](self._view))
