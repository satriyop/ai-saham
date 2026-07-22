"""Stateful Discover Candidate Discovery Workbench Screen.

Layer: Adapter

Milestone B — three functional tabs:
- Universe: locally-cached universe summary (flow/price/volume), explicit load.
- Accumulation: universe/window/squeeze/VWAP controls -> typed screen request.
- Saved / Compare: list saved watchlists and compare a selected snapshot against
  one fresh screen run (New / Dropped / Strengthening / Weakening / Unchanged).

Interaction contract (roadmap `docs/roadmap/roadmap_tui.md`):
- Selection, focus, sorting, and tab changes never start work.
- Only explicit actions (Run button / ``r`` / ``m`` toggle / ``c`` compare)
  execute a screen, universe load, or comparison.
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Select, Static

from src.adapters.tui.action_display import decorate_action
from src.adapters.tui.controllers.discover_controller import DiscoverController
from src.adapters.tui.presenters.discover_presenter import DiscoverPresenter, DiscoverViewModel
from src.adapters.tui.screens.save_watchlist_modal import SaveWatchlistModal
from src.adapters.tui.state import ScreenState, ScreenStatus
from src.adapters.tui.worker_lifecycle import dispatch_if_active
from src.application.use_case.compare_screen_watchlist_use_case import (
    CompareScreenWatchlistRequest,
)
from src.application.use_case.list_screen_watchlists_use_case import (
    ListScreenWatchlistsRequest,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowRequest,
)

_TAB_UNIVERSE = "UNIVERSE"
_TAB_ACCUMULATION = "ACCUMULATION"
_TAB_SAVED = "SAVED_COMPARE"

# Operation currently owning the shared worker/state slot; drives rendering.
_OP_UNIVERSE = "UNIVERSE"
_OP_ACCUM = "ACCUM"
_OP_LIST = "LIST"
_OP_COMPARE = "COMPARE"


class CandidateBrowserScreen(Screen[None]):
    """Render the Discover workspace: Universe, Accumulation, and Saved/Compare."""

    BINDINGS = [
        Binding("1", "app.show_today", "Today"),
        Binding("2", "app.show_candidates", "Candidates"),
        Binding("r", "run", "Run"),
        Binding("c", "compare", "Compare saved"),
        Binding("s", "save_shortlist", "Save shortlist"),
        Binding("m", "toggle_multi", "Toggle multi-window"),
        Binding("enter", "open_selected_ticker", "Open research"),
        Binding("escape", "pop_screen", "Back", show=False),
        Binding("j", "next_row", "Next", show=False),
        Binding("k", "prev_row", "Previous", show=False),
        Binding("down", "next_row", "Next", show=False),
        Binding("up", "prev_row", "Previous", show=False),
        Binding("[", "prev_tab", "Prev tab", show=False),
        Binding("]", "next_tab", "Next tab", show=False),
        Binding("?", "app.show_help", "Help"),
        Binding("h", "app.show_help", "Help", show=False),
    ]

    def __init__(
        self,
        controller: DiscoverController,
        presenter: DiscoverPresenter,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._presenter = presenter
        self._active_tab = _TAB_ACCUMULATION
        self._operation = _OP_ACCUM
        self._has_rendered_result = False
        # Per-tab row state so navigation and Enter act on the visible tab.
        self._candidate_rows: tuple[Any, ...] = ()
        self._universe_rows: tuple[Any, ...] = ()
        self._watchlist_summaries: tuple[Any, ...] = ()
        self._current_projection: Any = None
        self._last_request: RunAccumulationScreenWorkflowRequest | None = None
        self._selected_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="candidate-shell"):
            yield Static("Candidates", id="candidate-title")
            with Horizontal(id="discover-tab-bar"):
                yield Button("Universe", id="tab-universe", classes="tab-btn")
                yield Button("Accumulation", id="tab-accum", classes="tab-btn active-tab")
                yield Button("Saved / Compare", id="tab-saved", classes="tab-btn")

            with Horizontal(id="filter-toolbar"):
                yield Select(
                    [
                        ("LQ45", "lq45"),
                        ("IDX30", "idx30"),
                        ("IDX80", "idx80"),
                        ("BUMN20", "bumn20"),
                        ("JII", "jii"),
                    ],
                    value="lq45",
                    id="universe-select",
                    allow_blank=False,
                )
                yield Select(
                    [
                        ("7 Sessions", "7"),
                        ("30 Sessions", "30"),
                        ("90 Sessions", "90"),
                        ("Multi-Window", "multi"),
                    ],
                    value="7",
                    id="window-select",
                    allow_blank=False,
                )
                yield Checkbox("Squeeze", id="squeeze-check")
                yield Checkbox("VWAP Only", id="vwap-check")
                yield Button("Run", id="run-btn", variant="primary")
                yield Button("Save Shortlist", id="save-btn", variant="default")

            yield Static("IDLE — OFFLINE", id="candidate-status", classes="semantic-info")
            yield Static("", id="candidate-selected")

            with Horizontal(id="candidate-workspace"):
                with VerticalScroll(id="candidate-list"):
                    yield Static("Loading candidates...", id="candidate-table-content")
                with VerticalScroll(id="candidate-preview"):
                    yield Static(
                        "Select a candidate to view preview detail.", id="preview-content"
                    )

        yield Footer()

    def on_resize(self, event: Any) -> None:
        width = event.size.width if hasattr(event, "size") else getattr(self.size, "width", 80)
        if width >= 100:
            self.add_class("wide")
            self.remove_class("compact")
        else:
            self.add_class("compact")
            self.remove_class("wide")

    def on_mount(self) -> None:
        self.query_one("#candidate-list", VerticalScroll).focus()
        # Loading the default Accumulation view once on open is local, deterministic
        # compute (not a provider fetch); no control change triggers a rerun.
        self.action_run()

    # ------------------------------------------------------------------ helpers

    def _build_request(self) -> RunAccumulationScreenWorkflowRequest:
        uni_select = self.query_one("#universe-select", Select)
        win_select = self.query_one("#window-select", Select)
        squeeze = self.query_one("#squeeze-check", Checkbox).value
        vwap = self.query_one("#vwap-check", Checkbox).value

        universe = str(uni_select.value) if uni_select.value else "lq45"
        win_val = str(win_select.value) if win_select.value else "7"
        is_multi = win_val == "multi"
        window = 7 if is_multi else int(win_val)

        return RunAccumulationScreenWorkflowRequest(
            tickers=[],
            universe_label=universe,
            universe_name=universe,
            window=window,
            min_streak=0,
            # Filter policy is application/config-owned; the adapter does not invent
            # a minimum foreign-flow score. None means "use the configured default".
            min_foreign_flow_score=None,
            min_signal_score=None,
            min_piotroski=0,
            strategy_name=None,
            include_strategy_overlay=False,
            multi=is_multi,
            windows=[7, 30, 90] if is_multi else [],
            top=50,
            save_name=None,
            save_enabled=False,
            squeeze_only=bool(squeeze),
            vwap_only=bool(vwap),
        )

    def _selected_universe(self) -> str:
        sel = self.query_one("#universe-select", Select)
        return str(sel.value) if sel.value else "lq45"

    def _active_rows(self) -> tuple[Any, ...]:
        if self._active_tab == _TAB_UNIVERSE:
            return self._universe_rows
        if self._active_tab == _TAB_SAVED:
            return self._watchlist_summaries
        return self._candidate_rows

    # ------------------------------------------------------------------ actions

    def action_run(self) -> None:
        """Explicit Run: execute the active tab's operation once."""
        if self._active_tab == _TAB_UNIVERSE:
            self._start(_OP_UNIVERSE, self._execute_universe, self._selected_universe())
        elif self._active_tab == _TAB_SAVED:
            self._start(_OP_LIST, self._execute_list, ListScreenWatchlistsRequest())
        else:
            request = self._build_request()
            self._last_request = request
            self._start(_OP_ACCUM, self._execute_accumulation, request)

    def action_compare(self) -> None:
        """Explicit Compare: diff the selected saved snapshot against a fresh run."""
        if self._active_tab != _TAB_SAVED or not self._watchlist_summaries:
            return
        idx = min(self._selected_index, len(self._watchlist_summaries) - 1)
        name = self._watchlist_summaries[idx].name
        request = CompareScreenWatchlistRequest(
            name=name, screen_request=self._build_request()
        )
        self._start(_OP_COMPARE, self._execute_compare, request)

    def action_toggle_multi(self) -> None:
        # Explicit keypress: flip the window control and run once (Accumulation only).
        win_select = self.query_one("#window-select", Select)
        current = str(win_select.value) if win_select.value else "7"
        win_select.value = "7" if current == "multi" else "multi"
        self._activate_tab(_TAB_ACCUMULATION)
        self.action_run()

    def action_open_selected_ticker(self) -> None:
        rows = self._active_rows()
        if not rows or self._active_tab == _TAB_SAVED:
            return
        idx = min(self._selected_index, len(rows) - 1)
        self.app.action_open_ticker(rows[idx].ticker)

    def action_pop_screen(self) -> None:
        self.app.action_show_today()

    def action_next_row(self) -> None:
        rows = self._active_rows()
        if not rows:
            return
        self._selected_index = min(self._selected_index + 1, len(rows) - 1)
        self._render_selection(rows[self._selected_index])

    def action_prev_row(self) -> None:
        rows = self._active_rows()
        if not rows:
            return
        self._selected_index = max(self._selected_index - 1, 0)
        self._render_selection(rows[self._selected_index])

    def action_next_tab(self) -> None:
        order = [_TAB_UNIVERSE, _TAB_ACCUMULATION, _TAB_SAVED]
        self._switch_tab(order[(order.index(self._active_tab) + 1) % len(order)])

    def action_prev_tab(self) -> None:
        order = [_TAB_UNIVERSE, _TAB_ACCUMULATION, _TAB_SAVED]
        self._switch_tab(order[(order.index(self._active_tab) - 1) % len(order)])

    def action_save_shortlist(self) -> None:
        if not self._current_candidates():
            return

        def handle_save(name: str | None) -> None:
            result = self._perform_save(name)
            if result is not None:
                self.query_one("#candidate-status", Static).update(
                    f"Saved {result.saved_count} candidate(s) to shortlist '{result.name}'"
                )

        self.app.push_screen(SaveWatchlistModal(), handle_save)

    def _perform_save(self, name: str | None) -> Any:
        """Persist exactly the current canonical projection under ``name``.

        The saved universe/window come from the request that produced the shown
        projection — never a hardcoded default.
        """
        candidates = self._current_candidates()
        if not name or not candidates:
            return None
        request = self._last_request
        return self._controller.save_current_snapshot(
            name=name,
            candidates=candidates,
            universe=request.universe_label if request else "",
            window_days=request.window if request else 0,
        )

    def _current_candidates(self) -> list[Any]:
        projection = self._current_projection
        if projection is None:
            return []
        candidates = list(getattr(projection, "candidates", []) or [])
        if not candidates and hasattr(projection, "rows"):
            candidates = [row.candidate for row in projection.rows]
        return candidates

    # ------------------------------------------------------------------ tabs

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self.action_run()
        elif event.button.id == "save-btn":
            self.action_save_shortlist()
        elif event.button.id == "tab-universe":
            self._switch_tab(_TAB_UNIVERSE)
        elif event.button.id == "tab-accum":
            self._switch_tab(_TAB_ACCUMULATION)
        elif event.button.id == "tab-saved":
            self._switch_tab(_TAB_SAVED)

    def _switch_tab(self, tab: str) -> None:
        # Tab changes never start work: switching only re-renders already-held
        # state or shows an explicit "Press r/Run" prompt for that tab.
        self._activate_tab(tab)
        self._selected_index = 0
        prompt = {
            _TAB_UNIVERSE: "Press r / Run to load the universe view (offline, local cache).",
            _TAB_ACCUMULATION: "Press r / Run to screen for accumulation candidates.",
            _TAB_SAVED: "Press r / Run to list saved shortlists, then c to compare.",
        }[tab]
        self.query_one("#candidate-table-content", Static).update(prompt)
        self.query_one("#preview-content", Static).update(prompt)
        self.query_one("#candidate-selected", Static).update("")

    def _activate_tab(self, tab: str) -> None:
        self._active_tab = tab
        self._controller.workspace.active_tab = tab
        ids = {
            _TAB_UNIVERSE: "tab-universe",
            _TAB_ACCUMULATION: "tab-accum",
            _TAB_SAVED: "tab-saved",
        }
        for tab_key, button_id in ids.items():
            self.query_one(f"#{button_id}", Button).set_class(tab_key == tab, "active-tab")

    # ------------------------------------------------------------------ workers

    def _start(self, operation: str, runner: Any, request: Any) -> None:
        self._operation = operation
        generation = self._controller.begin()
        self._render_loading()
        runner(generation, request)

    @work(thread=True, exclusive=True)
    def _execute_accumulation(self, generation: int, request: Any) -> None:
        self._controller.execute_accumulation_generation(
            generation, request, dispatch=self._dispatch, listener=self._render_state
        )

    @work(thread=True, exclusive=True)
    def _execute_universe(self, generation: int, universe_label: str) -> None:
        self._controller.execute_universe_generation(
            generation, universe_label, dispatch=self._dispatch, listener=self._render_state
        )

    @work(thread=True, exclusive=True)
    def _execute_list(self, generation: int, request: Any) -> None:
        self._controller.execute_list_watchlists_generation(
            generation, request, dispatch=self._dispatch, listener=self._render_state
        )

    @work(thread=True, exclusive=True)
    def _execute_compare(self, generation: int, request: Any) -> None:
        self._controller.execute_compare_watchlist_generation(
            generation, request, dispatch=self._dispatch, listener=self._render_state
        )

    def _dispatch(self, callback: Any, *args: Any) -> Any:
        return dispatch_if_active(self.app, callback, *args)

    def cancel_active_work(self) -> None:
        self.workers.cancel_node(self)
        if self._controller.cancel_current():
            self.query_one("#candidate-status", Static).update(
                "IDLE — work cancelled; press r to retry"
            )

    # ------------------------------------------------------------------ render

    def _render_loading(self) -> None:
        status = self.query_one("#candidate-status", Static)
        status.update(f"LOADING — {self._operation.lower()}")
        status.set_classes("semantic-warning")

    def _set_status(self, text: str, css: str) -> None:
        status = self.query_one("#candidate-status", Static)
        status.update(text)
        status.set_classes(css)

    def _render_state(self, state: ScreenState) -> None:
        if state.status is ScreenStatus.LOADING:
            self._render_loading()
            return
        if state.status is ScreenStatus.ERROR:
            self._set_status("ERROR — retry with r", "semantic-error")
            self.query_one("#candidate-table-content", Static).update(
                f"{state.error_type}: {state.error_message}"
            )
            return
        if state.status not in {ScreenStatus.READY, ScreenStatus.EMPTY}:
            return

        self._selected_index = 0
        if self._operation == _OP_UNIVERSE:
            self._render_universe(state.payload)
        elif self._operation == _OP_LIST:
            self._render_watchlists(state.payload)
        elif self._operation == _OP_COMPARE:
            self._render_comparison(state.payload)
        else:
            self._render_accumulation(state.payload, state.status)
        self._has_rendered_result = True

    def _render_selection(self, row: Any) -> None:
        if self._active_tab == _TAB_UNIVERSE:
            self._render_universe_preview(row)
        elif self._active_tab == _TAB_ACCUMULATION:
            self._render_candidate_preview(row)

    # -- accumulation ---------------------------------------------------------

    def _render_accumulation(self, payload: Any, status: ScreenStatus) -> None:
        self._current_projection = payload
        view = self._presenter.present_accumulation(payload)
        self._candidate_rows = view.candidate_rows
        if not view.candidate_rows or status is ScreenStatus.EMPTY:
            self._set_status("EMPTY — 0 candidates found", "semantic-info")
        else:
            self._set_status(
                f"READY — {len(view.candidate_rows)} candidate(s)", "semantic-ready"
            )
        self.query_one("#candidate-table-content", Static).update(
            self._accumulation_table(view)
        )
        if view.candidate_rows:
            self._render_candidate_preview(view.candidate_rows[0])
        else:
            self.query_one("#candidate-selected", Static).update(
                "Action: - | Risk: UNKNOWN | Data: EMPTY"
            )

    def _accumulation_table(self, view: DiscoverViewModel) -> str:
        if not view.candidate_rows:
            return "No matching candidates found."
        lines = [
            "  #   Ticker Flow%  Streak Risk   Action      Signal   Details",
            "───  ────── ─────  ────── ────── ─────────── ──────── ─────────────",
        ]
        for row in view.candidate_rows:
            signal = row.signal_score if row.signal_score is not None else "-"
            detail = row.window_shape_label or row.setup_phase or ""
            lines.append(
                f"│ {row.canonical_rank:<2}  {row.ticker:<6} {row.flow_score:5.1f}   "
                f"{row.consecutive_streak:<6} {row.risk_status:<6} "
                f"{decorate_action(row.action):<11} {signal:>6}   {detail}"
            )
        return "\n".join(lines)

    def _render_candidate_preview(self, row: Any) -> None:
        self.query_one("#candidate-selected", Static).update(
            f"Selected: {row.ticker} | Action: {row.action or '-'} | "
            f"Risk: {row.risk_status} | Data: ALIGNED"
        )
        self.query_one("#preview-content", Static).update(
            "SELECTED CANDIDATE PREVIEW\n"
            f"Ticker             : {row.ticker}\n"
            f"Canonical Rank     : #{row.canonical_rank}\n"
            f"Foreign Flow Score : {row.flow_score:.1f}\n"
            f"Consecutive Streak : {row.consecutive_streak} session(s)\n"
            f"Setup Phase        : {row.setup_phase or '-'}\n"
            f"Risk Status        : {row.risk_status}\n"
            f"Canonical Action   : {row.action or '-'}\n"
            f"Signal Coverage    : {row.signal_authority_coverage or '-'}"
        )

    # -- universe -------------------------------------------------------------

    def _render_universe(self, result: Any) -> None:
        rows = tuple(getattr(result, "rows", ()) or ())
        self._universe_rows = rows
        if not rows:
            self._set_status(
                f"EMPTY — no cached data for {getattr(result, 'universe_name', '')}",
                "semantic-info",
            )
            self.query_one("#candidate-table-content", Static).update(
                "No locally cached universe data.\n"
                "Update market data first (CLI: saham fetch market)."
            )
            self.query_one("#candidate-selected", Static).update("")
            return
        self._set_status(
            f"READY — {getattr(result, 'ticker_count', len(rows))} tickers "
            f"| missing candles {getattr(result, 'missing_candles', 0)} "
            f"| missing flow {getattr(result, 'missing_flow', 0)}",
            "semantic-ready",
        )
        self.query_one("#candidate-table-content", Static).update(self._universe_table(rows))
        self._render_universe_preview(rows[0])

    def _universe_table(self, rows: tuple[Any, ...]) -> str:
        lines = [
            "Ticker  Close      Chg%    Volume        FgnNet         FgnRatio",
            "──────  ─────────  ──────  ────────────  ─────────────  ────────",
        ]
        for r in rows:
            close = f"{r.last_close:,.0f}" if r.last_close is not None else "—"
            chg = f"{r.change_pct:+.2f}" if r.change_pct is not None else "—"
            vol = f"{r.volume:,}" if r.volume is not None else "—"
            fnet = f"{r.foreign_net_value:,.0f}" if r.foreign_net_value is not None else "—"
            fratio = (
                f"{r.foreign_flow_ratio:+.2f}" if r.foreign_flow_ratio is not None else "—"
            )
            lines.append(
                f"{r.ticker:<6}  {close:>9}  {chg:>6}  {vol:>12}  {fnet:>13}  {fratio:>8}"
            )
        return "\n".join(lines)

    def _render_universe_preview(self, row: Any) -> None:
        # Missing inputs render as explicit "— unavailable" (never zero-filled).
        na = "— unavailable"
        close = str(row.last_close) if row.last_close is not None else na
        chg = f"{row.change_pct:+.2f}" if row.change_pct is not None else na
        vol = f"{row.volume:,}" if row.volume is not None else na
        fnet = str(row.foreign_net_value) if row.foreign_net_value is not None else na
        fratio = (
            f"{row.foreign_flow_ratio:+.2f}" if row.foreign_flow_ratio is not None else na
        )
        head_chg = f"{row.change_pct:+.2f}%" if row.change_pct is not None else "—"
        head_close = row.last_close if row.last_close is not None else "—"
        self.query_one("#candidate-selected", Static).update(
            f"Selected: {row.ticker} | Close: {head_close} | Chg: {head_chg}"
        )
        self.query_one("#preview-content", Static).update(
            "UNIVERSE ROW\n"
            f"Ticker        : {row.ticker}\n"
            f"Name          : {row.name or '-'}\n"
            f"Sector        : {row.sector or '-'}\n"
            f"Last Close    : {close}\n"
            f"Change %      : {chg}\n"
            f"Volume        : {vol}\n"
            f"Foreign Net   : {fnet}\n"
            f"Foreign Ratio : {fratio}\n"
            f"Latest Date   : {row.latest_date or na}"
        )

    # -- saved / compare ------------------------------------------------------

    def _render_watchlists(self, result: Any) -> None:
        view = self._presenter.present_watchlists(result)
        summaries = view.watchlist_summaries
        self._watchlist_summaries = summaries
        if not summaries:
            self._set_status("EMPTY — no saved shortlists", "semantic-info")
            self.query_one("#candidate-table-content", Static).update(
                "No saved shortlists yet. Screen candidates on the Accumulation tab and Save one."
            )
            self.query_one("#candidate-selected", Static).update("")
            self.query_one("#preview-content", Static).update("")
            return
        self._set_status(f"READY — {len(summaries)} saved shortlist(s)", "semantic-ready")
        lines = [
            "Name                 Saved              Universe  Window  Tickers",
            "───────────────────  ─────────────────  ────────  ──────  ───────",
        ]
        for s in summaries:
            saved = s.latest_saved_at.strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"{s.name:<20.20} {saved:<18} {s.universe:<8.8}  {s.window_days:>5}d  "
                f"{s.ticker_count:>6}"
            )
        self.query_one("#candidate-table-content", Static).update("\n".join(lines))
        self.query_one("#candidate-selected", Static).update(
            f"Selected: {summaries[0].name} — press c to compare vs a fresh screen run"
        )
        self.query_one("#preview-content", Static).update(
            "SAVED SHORTLIST\n"
            "Select a shortlist (j/k) and press c to compare it against a fresh\n"
            "accumulation screen using the current filter controls."
        )

    def _render_comparison(self, result: Any) -> None:
        view = self._presenter.present_comparison(result)
        comp = result.comparison
        self._set_status(
            f"READY — compare '{comp.snapshot_name}' "
            f"(saved {comp.snapshot_count} vs fresh {comp.fresh_count})",
            "semantic-ready",
        )
        groups = [
            ("+ New", comp.new_tickers),
            ("- Dropped", comp.dropped_tickers),
            ("▲ Strengthening", [c.ticker for c in comp.strengthening]),
            ("▼ Weakening", [c.ticker for c in comp.weakening]),
            ("= Unchanged", [c.ticker for c in comp.unchanged]),
        ]
        lines: list[str] = []
        for label, tickers in groups:
            names = ", ".join(tickers) if tickers else "—"
            lines.append(f"{label:<16} ({len(tickers):>2}): {names}")
        for warning in view.warnings:
            lines.append(f"! {warning}")
        self.query_one("#candidate-table-content", Static).update("\n".join(lines))
        self.query_one("#preview-content", Static).update(
            "COMPARISON GROUPS\n"
            "+ new    - dropped    ▲ strengthening    ▼ weakening    = unchanged\n"
            "Symbols and text carry meaning without relying on color."
        )
        self.query_one("#candidate-selected", Static).update(
            f"Compared '{comp.snapshot_name}' against one fresh screen run."
        )
