"""OpenCode-style daily cockpit Textual app (optional TUI adapter).

Phases: shell/palette (0–1), boards (2–3), plan/fetch (4), harden (5).
Design: docs/design/tui-cockpit-opencode.md · ADR-051

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.timer import Timer
from textual.widgets import DataTable, Input, Static

from src.adapters.composition.board_snapshot_store import (
    invalidate_accum_board_snapshot,
    read_accum_board_snapshot,
    write_accum_board_snapshot,
)
from src.adapters.tui.board_load_policy import (
    recomputing_status_note,
    should_blank_board_for_load,
    snapshot_freshness_note,
)
from src.adapters.tui.board_snapshot import (
    board_view_from_snapshot,
    identity_from_live_payload,
    snapshot_from_board_view,
)
from src.adapters.tui.screens.help import HelpModal
from src.adapters.tui.screens.palette import CommandPalette
from src.adapters.tui.state import ScreenState, ScreenStatus
from src.adapters.tui.theme import COCKPIT_CSS
from src.adapters.tui.worker_lifecycle import dispatch_if_active

# Injected callables (composition). Phase 0–1 may leave these None.
AccumLoader = Callable[[], Any]
PreOpenLoader = Callable[[], Any]
PlanRunner = Callable[[str], Any]
FetchPreviewer = Callable[[], Any]
FetchRunner = Callable[[], Any]
TickerDetailLoader = Callable[[str], Any]
AgentTurnRunner = Callable[[Any], Any]

BoardKind = Literal["accum", "preopen", "none"]
DetailReturnStage = Literal["accum", "preopen", "shell", "broker-list"]


class CockpitApp(App[None]):
    """Daily cockpit — layout B (main stage + context sidebar + status)."""

    TITLE = "ai-saham"
    SUB_TITLE = "cockpit"
    CSS = COCKPIT_CSS

    BINDINGS = [
        Binding("ctrl+p", "command_palette", "Commands", show=True, priority=True),
        Binding("ctrl+b", "toggle_sidebar", "Sidebar", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
        Binding("r", "refresh_local", "Refresh", show=False),
        Binding("p", "plan_swing", "Plan", show=False),
        # Do NOT use priority=True on Enter — it steals Enter from CommandPalette
        # (and other modals) so palette commands never run.
        Binding("enter", "view_ticker", "View", show=False),
        Binding("escape", "go_back", "Back", show=False),
        # List / board rows: arrows only (design lock — not vim j/k)
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        # Desk hub keys (no-op outside broker show/deep pages)
        Binding("t", "broker_top", "Desk top", show=False),
        Binding("f", "broker_flow", "Desk flow", show=False),
        Binding("h", "broker_history", "Desk history", show=False),
        Binding("m", "broker_matrix", "Desk matrix", show=False),
        Binding("c", "broker_calendar", "Desk calendar", show=False),
        # `v` is chord prefix off desk hub (v t / v b); on desk hub = jump ticker
        # (handled in on_key so prefix chords do not fight single-key v).
        Binding("b", "ticker_job_brokers", "Ticker brokers", show=False),
        Binding("o", "ticker_job_foreign", "Ticker foreign", show=False),
        Binding("x", "ticker_job_dist", "Ticker dist", show=False),
        Binding("n", "ticker_job_fin", "Ticker fin", show=False),
        # Fin period grain · binary toggle · armed only while fin job front
        Binding("y", "toggle_fin_period", "Fin period", show=False),
        Binding("d", "toggle_detail", "Detail", show=False),
        # Prompt rail: : = generic focus; / = agent stage (OpenCode-style)
        Binding("colon", "focus_prompt", "Prompt", show=False),
        Binding("slash", "focus_agent", "Agent", show=False),
        # ``j`` is Judge re-judge only (on_key) — never board list navigation.
        Binding("q", "quit", "Quit", show=True),
    ]

    # Two-key chords (OpenCode-style labels in palette). Textual has no native
    # sequences — first key arms a short prefix; second key dispatches.
    _CHORD_HINTS = {
        "s": "s a screen · s p pre-open",
        "v": "v t ticker · v b broker",
    }
    _CHORD_MAP = {
        ("s", "a"): "screen-accum",
        ("s", "p"): "screen-preopen",
        ("v", "t"): "view-ticker",
        ("v", "b"): "view-broker",
    }
    _CHORD_TIMEOUT_S = 1.0

    def __init__(
        self,
        *,
        accum_loader: AccumLoader | None = None,
        preopen_loader: PreOpenLoader | None = None,
        plan_runner: PlanRunner | None = None,
        fetch_previewer: FetchPreviewer | None = None,
        fetch_runner: FetchRunner | None = None,
        ticker_detail_loader: TickerDetailLoader | None = None,
        broker_list_loader: Callable[[], Any] | None = None,
        broker_show_loader: Callable[[str], Any] | None = None,
        broker_top_loader: Callable[[str], Any] | None = None,
        broker_flow_loader: Callable[[str], Any] | None = None,
        broker_history_loader: Callable[[str], Any] | None = None,
        broker_matrix_loader: Callable[[str], Any] | None = None,
        broker_calendar_loader: Callable[[str], Any] | None = None,
        ticker_desks_loader: Callable[[str], Any] | None = None,
        ticker_job_loader: Callable[..., Any] | None = None,
        accum_controller: Any | None = None,
        preopen_controller: Any | None = None,
        accum_presenter: Any | None = None,
        preopen_presenter: Any | None = None,
        board_snapshot_path: Path | str | None = None,
        snapshot_universe: str = "lq45",
        ticker_judge_loader: Callable[[str], Any] | None = None,
        cache_health_loader: Callable[[], Any] | None = None,
        paper_log_runner: Callable[[str], Any] | None = None,
        phase_history_loader: Callable[[str, Any], Any] | None = None,
        agent_turn_runner: AgentTurnRunner | None = None,
        agent_provider: str = "deepseek",
        agent_provider_available: bool = False,
    ) -> None:
        super().__init__()
        self._accum_loader = accum_loader
        self._preopen_loader = preopen_loader
        self._plan_runner = plan_runner
        self._fetch_previewer = fetch_previewer
        self._fetch_runner = fetch_runner
        self._ticker_detail_loader = ticker_detail_loader
        self._broker_list_loader = broker_list_loader
        self._broker_show_loader = broker_show_loader
        self._broker_top_loader = broker_top_loader
        self._broker_flow_loader = broker_flow_loader
        self._broker_history_loader = broker_history_loader
        self._broker_matrix_loader = broker_matrix_loader
        self._broker_calendar_loader = broker_calendar_loader
        self._ticker_desks_loader = ticker_desks_loader
        self._ticker_job_loader = ticker_job_loader
        self._ticker_judge_loader = ticker_judge_loader
        self._cache_health_loader = cache_health_loader
        self._paper_log_runner = paper_log_runner
        self._phase_history_loader = phase_history_loader
        self._agent_turn_runner = agent_turn_runner
        self._agent_provider = agent_provider
        self._agent_provider_available = agent_provider_available
        self._accum_controller = accum_controller
        self._preopen_controller = preopen_controller
        self._accum_presenter = accum_presenter
        self._preopen_presenter = preopen_presenter
        self._board_snapshot_path = (
            Path(board_snapshot_path) if board_snapshot_path is not None else None
        )
        self._snapshot_universe = (snapshot_universe or "lq45").strip().lower()

        self._sidebar_visible = True
        # shell | empty | accum | preopen | broker-list | detail | plan | loading | error
        self._stage = "shell"
        self._board_kind: BoardKind = "none"
        self._detail_return_stage: DetailReturnStage = "shell"
        self._broker_list_return: DetailReturnStage = "shell"
        self._broker_desk_code: str | None = None
        self._broker_page: str | None = None  # list|show|top|flow|history|matrix|cal|None
        self._broker_jump_ticker: str | None = None
        self._broker_desk_home_model: Any | None = None
        self._broker_desk_matrix_model: Any | None = None
        self._broker_desk_top_model: Any | None = None
        self._broker_desk_flow_model: Any | None = None
        self._broker_desk_history_model: Any | None = None
        self._broker_desk_calendar_model: Any | None = None
        self._ticker_detail_open: bool = False
        self._ticker_job: str | None = None  # brokers|flow|foreign|dist|fin while job open
        self._ticker_job_text: Any | None = None
        # Fin period grain · CLI --period quarterly|annual · job-local arm for y
        self._ticker_fin_period: str = "quarterly"
        self._judge_detail_open: bool = False
        self._preopen_detail_open: bool = False
        self._prompt_mode: str = "idle"  # idle | agent | cli (display only)
        self._view_from_desk: bool = False
        self._desk_entry: str | None = None  # broker-list | ticker-desks
        self._ticker_desks_stock: str | None = None  # stock for ticker→desks page
        self._mode = "local-first"
        self._focus_ticker = "—"
        self._status_note = "ctrl+p commands"
        self._rows: list[Any] = []
        self._row_index = 0
        self._broker_rows: list[Any] = []
        self._broker_row_index = 0
        self._detail_text = ""
        self._error_text = ""
        self._evidence_text = ""
        self._meta = "local-first · Ctrl+P · no silent network"
        self._board_title = "Cockpit · shell"
        self._board_summary = ""
        self._effective_session: Any | None = None
        self._market_context: Any | None = None
        self._preopen_snapshot_date: str = ""
        self._preopen_warnings: tuple[str, ...] = ()
        self._preopen_session_strip: Any | None = None
        self._plan_ticker: str = ""
        self._plan_result: str = ""
        self._plan_structure: Any | None = None
        self._plan_running: bool = False
        self._paper_outcome: str = ""
        self._paper_tape: list[Any] = []
        self._ticker_desk_model: Any | None = None
        self._chord_prefix: str | None = None
        self._chord_timer: Timer | None = None
        # Board load UX: keep prior rows while recomputing; snapshot on open.
        self._recomputing = False
        self._board_source: Literal["none", "live", "snapshot"] = "none"
        self._snapshot_freshness = ""
        self._judge_generation = 0
        self._agent_generation = 0
        self._agent_loading = False
        self._agent_stage_open = False
        self._agent_last_question = ""
        self._agent_last_good: dict | None = None
        self._judge_ticker = ""
        self._judge_limited = False
        self._cache_health: Any | None = None
        self._cache_next_step = "Fetch is explicit."
        # One-shot Online line after explicit fetch (does not replace Cache health).
        self._online_note: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
            with Vertical(id="main"):
                with Horizontal(id="main-header"):
                    with Vertical():
                        yield Static(self._board_title, id="view-title")
                        yield Static(f"· {self._meta}", id="view-meta")
                    yield Static(self._mode_label(), id="mode-pill")
                with Vertical(id="stage"):
                    with VerticalScroll(id="stage-scroll"):
                        yield Static(self._shell_body(), id="stage-body")
                        from src.adapters.tui.widgets.agent_commentary import AgentCommentary
                        from src.adapters.tui.widgets.broker_desk import BrokerDesk
                        from src.adapters.tui.widgets.broker_flow_desk import (
                            BrokerFlowDesk,
                        )
                        from src.adapters.tui.widgets.broker_history_desk import (
                            BrokerHistoryDesk,
                        )
                        from src.adapters.tui.widgets.broker_matrix_desk import (
                            BrokerMatrixDesk,
                        )
                        from src.adapters.tui.widgets.broker_top_desk import BrokerTopDesk
                        from src.adapters.tui.widgets.judge_desk import JudgeDesk
                        from src.adapters.tui.widgets.plan_desk import PlanDesk
                        from src.adapters.tui.widgets.ticker_desk import TickerDesk

                        yield JudgeDesk(id="judge-desk")
                        yield AgentCommentary(id="agent-commentary")
                        yield PlanDesk(id="plan-desk")
                        yield TickerDesk(id="ticker-desk")
                        yield BrokerDesk(id="broker-desk")
                        yield BrokerMatrixDesk(id="broker-matrix-desk")
                        yield BrokerTopDesk(id="broker-top-desk")
                        from src.adapters.tui.widgets.broker_calendar_desk import (
                            BrokerCalendarDesk,
                        )

                        yield BrokerFlowDesk(id="broker-flow-desk")
                        yield BrokerHistoryDesk(id="broker-history-desk")
                        yield BrokerCalendarDesk(id="broker-calendar-desk")
                        from src.adapters.tui.widgets.preopen_inspect_desk import (
                            PreopenInspectDesk,
                        )

                        yield PreopenInspectDesk(id="preopen-inspect-desk")
                        from src.adapters.tui.widgets.health_poster_desk import (
                            HealthPosterDesk,
                        )
                        from src.adapters.tui.widgets.paper_desk import PaperDesk

                        yield PaperDesk(id="paper-desk")
                        yield HealthPosterDesk(id="health-poster-desk")
                    # Mock src-badge (snapshot|live) above dense board table
                    yield Static("", id="board-source-badge", classes="hide")
                    # Broker list / stock desks: honesty in title+meta only (no chips)
                    yield DataTable(id="board-table")
                    yield Static("", id="evidence-strip")
                    yield Static(self._footer_hint(), id="board-footer")
                    # OpenCode 2-row composer · left brass · roomy pad above/below
                    with Vertical(id="prompt-rail"):
                        with Horizontal(id="prompt-row-input"):
                            yield Static("›", id="prompt-affordance")
                            # compact: no Textual tall focus border (ghost green box)
                            yield Input(
                                placeholder="type CLI or ask agent… · : or / to focus",
                                id="prompt-input",
                                compact=True,
                            )
                        # Vertical air between typed line and mode meta
                        yield Static("", id="prompt-row-gap")
                        with Horizontal(id="prompt-row-meta"):
                            yield Static("idle", id="prompt-mode")
                            yield Static(
                                "· local · design only · not wired",
                                id="prompt-sub",
                            )
            with Vertical(id="sidebar"):
                yield Static("Session", classes="side-title first")
                yield Static("Market   IDX", classes="side-line")
                yield Static(f"Mode     {self._mode}", classes="side-line", id="side-mode")
                yield Static("Cache    —", classes="side-line", id="side-cache")
                yield Static("Today", classes="side-title")
                yield Static("Pre-open —", classes="side-line", id="side-preopen")
                yield Static("Accum    —", classes="side-line", id="side-accum")
                yield Static("Focus", classes="side-title")
                yield Static("none selected", classes="side-line", id="side-focus")
                yield Static("Keys", classes="side-title")
                yield Static("ctrl+p  commands", classes="side-line")
                yield Static("enter   judge", classes="side-line")
                yield Static("j       re-judge", classes="side-line")
                yield Static("p       plan", classes="side-line")
                yield Static("r       refresh local", classes="side-line")
                yield Static("ctrl+b  sidebar", classes="side-line")
                yield Static("Online", classes="side-title")
                yield Static("Offline by default.", classes="side-line", id="side-offline")
                yield Static("Fetch is explicit.", classes="side-line", id="side-online")
        yield Static(self._status_text(), id="status")

    def on_mount(self) -> None:
        table = self.query_one("#board-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = False
        table.display = False
        try:
            self.query_one("#judge-desk").display = False
        except Exception:
            pass
        try:
            self.query_one("#plan-desk").display = False
        except Exception:
            pass
        try:
            self.query_one("#ticker-desk").display = False
        except Exception:
            pass
        self.query_one("#evidence-strip", Static).display = False
        # Src-badge: hide immediately so empty border never flashes
        try:
            badge = self.query_one("#board-source-badge", Static)
            badge.add_class("hide")
            badge.display = False
        except Exception:
            pass
        self._refresh_local_cache_health()
        self._refresh_chrome()
        # Live cockpit: open on local accumulation board (not a design manifesto).
        # Still local-first — no network until explicit Fetch.
        # Prefer last-run snapshot for instant paint, then recompute in background.
        if self._accum_controller is not None or self._accum_loader is not None:
            restored = self._try_restore_accum_snapshot()
            self._load_accum(keep_prior=restored)
        else:
            self._stage = "shell"
            self._board_title = "Cockpit"
            self._meta = "no loader · Ctrl+P for commands"
            self._refresh_chrome()

    # ── chrome ─────────────────────────────────────────────

    def _mode_label(self) -> str:
        if self._recomputing:
            return "● recomputing"
        if self._board_source == "snapshot" and self._stage == "accum":
            from src.adapters.tui.chrome_cues import snapshot_mode_label

            return snapshot_mode_label()
        return f"● {self._mode}"

    def _paint_board_source_badge(self) -> None:
        """Mock ``src-badge`` above the accum board (snapshot|live). Hidden elsewhere.

        Empty/hidden must not leave a bordered hollow (ghost green box).
        """
        from src.adapters.tui.chrome_cues import (
            accum_source_badge_kind,
            accum_source_badge_text,
        )

        badge = self.query_one("#board-source-badge", Static)
        badge.remove_class("snap")
        badge.remove_class("live")

        def _hide() -> None:
            badge.update("")
            badge.add_class("hide")
            badge.display = False

        if self._stage != "accum":
            _hide()
            return
        text = (
            accum_source_badge_text(
                board_source=self._board_source,
                recomputing=self._recomputing,
            )
            or ""
        ).strip()
        kind = accum_source_badge_kind(board_source=self._board_source)
        if not text or kind == "hide":
            _hide()
            return
        badge.remove_class("hide")
        badge.update(text)
        badge.display = True
        badge.add_class(kind)

    def _status_text(self) -> str:
        mode = "recomputing" if self._recomputing else self._mode
        if self._board_source == "snapshot" and not self._recomputing and self._stage == "accum":
            mode = "snapshot · limited judge"
        return (
            f"Cockpit · {self._stage} · {self._focus_ticker}  ·  "
            f"{mode}  ·  {self._status_note}  ·  ai-saham tui"
        )

    def _footer_hint(self) -> str:
        if self._stage == "empty":
            cue = self._cache_next_step if self._cache_next_step else "Ctrl+P · Fetch market data"
            return f"{cue} · no invented rows"
        if self._stage == "loading":
            from src.adapters.tui.chrome_cues import (
                broker_list_loading_footer,
                is_broker_list_loading,
            )

            if is_broker_list_loading(
                stage=self._stage,
                board_title=self._board_title,
                status_note=self._status_note,
            ):
                return broker_list_loading_footer()
            return "loading local cache… · wait · no silent network"
        if self._stage == "accum" and self._recomputing:
            return (
                "recomputing local board… · prior rows still shown · "
                "↑↓ ok · r restarts refresh · Ctrl+P"
            )
        if self._stage == "accum" and self._board_source == "snapshot":
            from src.adapters.tui.chrome_cues import snapshot_accum_footer

            return snapshot_accum_footer(freshness=self._snapshot_freshness)
        if self._stage == "accum":
            return (
                "↑↓ move · Enter judge · p plan · r refresh · Ctrl+P  ·  "
                "ranked by Signal (not Accum) · Ctrl+P pre-open to switch board"
            )
        if self._stage == "preopen" and self._recomputing:
            return "recomputing pre-open… · prior rows still shown · r restarts · Ctrl+P"
        if self._stage == "preopen":
            return (
                "↑↓ move · Enter inspect · p plan · r refresh · Ctrl+P  ·  "
                "IEV snapshot board · Enter = present-only inspect"
            )
        if self._stage == "broker-list":
            if any(getattr(r, "has_partial_netx", False) for r in self._broker_rows):
                return (
                    "↑↓ · Enter desk · esc · Ctrl+P · thin NetX = fewer sessions than window label"
                )
            return "↑↓ move · Enter desk home · esc back · Ctrl+P · tracked desks"
        if self._stage == "ticker-desks":
            if any(getattr(r, "has_partial_netx", False) for r in self._broker_rows):
                return "↑↓ · Enter desk · esc ticker · thin NetX = fewer sessions than window label"
            return (
                "↑↓ move · Enter desk home · esc → ticker · Ctrl+P · stock desks · Net3/5/7/10/20"
            )
        if self._stage == "detail" and self._broker_page in {
            "show",
            "top",
            "flow",
            "history",
            "matrix",
        }:
            return (
                "↑↓ scroll · t top · f flow · c cal · h history · m matrix · "
                "v view ticker · esc desk trail · Ctrl+P"
            )
        if self._stage == "detail" and self._status_note == "view ticker":
            return "↑↓ scroll · b f o x n jobs · d detail · p plan · esc trail · Ctrl+P · Tab chips"
        if self._stage == "detail" and str(self._status_note or "").startswith("view ticker "):
            # Job surface: density not contextual — no d in footer strip
            job = str(self._ticker_job or "").strip()
            y_bit = " · y period" if job == "fin" else ""
            return f"↑↓ · b f o x n jobs{y_bit} · p plan · esc show · Ctrl+P · Tab chips"
        if self._stage == "detail" and self._status_note in {"judge", "re-judging"}:
            if self._judge_limited:
                return (
                    "↑↓ scroll · d detail · j re-judge local · r live board · p plan · "
                    "esc · Ctrl+P  ·  limited judge · j or r for full desk"
                )
            return (
                "↑↓ scroll · j re-judge local · p plan · esc board · Ctrl+P  ·  "
                "present-only judge · same object as board"
            )
        if self._stage == "detail":
            return "↑↓/PgUp/PgDn scroll · esc back · p plan · Ctrl+P"
        if self._stage == "plan":
            return "↑↓ scroll · esc back · p re-run · l paper log · Ctrl+P · no broker order"
        return "Ctrl+P commands · ? help · q quit"

    def _shell_body(self) -> str:
        return (
            "[bold #e8e8e8]Starting cockpit…[/]\n\n"
            "Loading [bold]Screen · accumulation[/] from local cache.\n"
            "No network on open — Fetch is explicit via Ctrl+P.\n\n"
            "[dim]Ctrl+P commands · ? help · q quit[/]"
        )

    def _empty_body(self) -> str:
        from src.adapters.tui.empty_stage_body import format_empty_stage_body

        status = getattr(self._cache_health, "status", None)
        next_step = (
            getattr(self._cache_health, "next_step", None)
            or self._cache_next_step
            or "Ctrl+P · Fetch market data (explicit)"
        )
        return format_empty_stage_body(
            cache_status=str(status) if status is not None else None,
            board_title=self._board_title,
            meta=self._meta,
            board_kind=str(self._board_kind or "none"),
            next_step=str(next_step),
        )

    def _hide_judge_desk(self) -> None:
        try:
            desk = self.query_one("#judge-desk")
            desk.display = False
        except Exception:
            pass

    def _invalidate_agent_turn(self) -> None:
        self._agent_generation += 1
        self._agent_loading = False
        self._agent_last_question = ""
        if self._agent_stage_open:
            self._exit_agent_stage(refresh=False)
        try:
            self.query_one("#agent-commentary").clear()
        except Exception:
            pass

    def _hide_agent_commentary(self) -> None:
        try:
            desk = self.query_one("#agent-commentary")
            desk.display = False
            desk.set_stage_mode(False)
        except Exception:
            pass

    def _enter_agent_stage(self, *, ready: bool = True) -> None:
        """Replace main stage with agent surface (OpenCode-style)."""
        from src.adapters.tui.widgets.agent_commentary import AgentCommentary

        self._agent_stage_open = True
        self._set_prompt_mode_chip("agent")
        try:
            body = self.query_one("#stage-body", Static)
            scroll = self.query_one("#stage-scroll", VerticalScroll)
            table = self.query_one("#board-table", DataTable)
            evidence = self.query_one("#evidence-strip", Static)
            body.display = False
            table.display = False
            evidence.display = False
            scroll.display = True
            self._hide_instrument_desks()
            commentary = self.query_one("#agent-commentary", AgentCommentary)
            commentary.set_stage_mode(True)
            if ready:
                ticker = str(self._focus_ticker or "—").upper()
                action = "—"
                row = self._rows[self._row_index] if self._rows else None
                source = getattr(row, "source", None) if row is not None else None
                setup = getattr(source, "trade_setup", None) if source is not None else None
                if setup is not None:
                    raw = getattr(setup, "action", None)
                    action = getattr(raw, "value", None) or str(raw or "—")
                commentary.show_stage_ready(
                    ticker=ticker,
                    action=str(action),
                    provider=self._agent_provider,
                )
            try:
                self.query_one("#view-title", Static).update(
                    f"Agent · {str(self._focus_ticker or '—').upper()}"
                )
                self.query_one("#view-meta", Static).update(
                    "· non-authoritative · Esc leave · Enter send"
                )
                self.query_one("#board-footer", Static).update(
                    "Agent stage · deterministic Judge unchanged · Esc back · / re-focus"
                )
            except Exception:
                pass
        except Exception:
            self._agent_stage_open = False

    def _exit_agent_stage(self, *, refresh: bool = True) -> None:
        """Leave agent stage and restore prior board/judge chrome."""
        was_open = self._agent_stage_open
        self._agent_stage_open = False
        self._agent_last_question = ""
        self._hide_agent_commentary()
        if was_open and refresh:
            try:
                self._refresh_chrome()
            except Exception:
                pass

    def _hide_plan_desk(self) -> None:
        try:
            desk = self.query_one("#plan-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_ticker_desk(self) -> None:
        try:
            desk = self.query_one("#ticker-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_broker_desk(self) -> None:
        try:
            desk = self.query_one("#broker-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_broker_matrix_desk(self) -> None:
        try:
            desk = self.query_one("#broker-matrix-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_broker_top_desk(self) -> None:
        try:
            desk = self.query_one("#broker-top-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_broker_flow_desk(self) -> None:
        try:
            desk = self.query_one("#broker-flow-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_broker_history_desk(self) -> None:
        try:
            desk = self.query_one("#broker-history-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_broker_calendar_desk(self) -> None:
        try:
            desk = self.query_one("#broker-calendar-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_preopen_inspect_desk(self) -> None:
        try:
            desk = self.query_one("#preopen-inspect-desk")
            desk.display = False
        except Exception:
            pass

    def _hide_paper_desk(self) -> None:
        try:
            self.query_one("#paper-desk").display = False
        except Exception:
            pass

    def _hide_health_poster_desk(self) -> None:
        try:
            self.query_one("#health-poster-desk").display = False
        except Exception:
            pass

    def _hide_instrument_desks(self) -> None:
        self._hide_judge_desk()
        self._hide_plan_desk()
        self._hide_ticker_desk()
        self._hide_broker_desk()
        self._hide_broker_matrix_desk()
        self._hide_broker_top_desk()
        self._hide_broker_flow_desk()
        self._hide_broker_history_desk()
        self._hide_broker_calendar_desk()
        self._hide_preopen_inspect_desk()
        self._hide_paper_desk()
        self._hide_health_poster_desk()
        if not self._agent_stage_open:
            self._hide_agent_commentary()

    def _paint_detail_stage(self, *, body: Static, scroll: VerticalScroll) -> None:
        """Detail stage: Judge / ticker / broker visual desks; text body otherwise."""
        from src.adapters.tui.widgets.broker_calendar_desk import BrokerCalendarDesk
        from src.adapters.tui.widgets.broker_desk import BrokerDesk
        from src.adapters.tui.widgets.broker_flow_desk import BrokerFlowDesk
        from src.adapters.tui.widgets.broker_history_desk import BrokerHistoryDesk
        from src.adapters.tui.widgets.broker_matrix_desk import BrokerMatrixDesk
        from src.adapters.tui.widgets.broker_top_desk import BrokerTopDesk
        from src.adapters.tui.widgets.judge_desk import JudgeDesk
        from src.adapters.tui.widgets.preopen_inspect_desk import PreopenInspectDesk
        from src.adapters.tui.widgets.ticker_desk import TickerDesk

        is_judge = self._status_note in {"judge", "re-judging"} and (
            self._board_kind == "accum" or self._detail_return_stage == "accum"
        )
        is_preopen_inspect = self._status_note == "inspect" and (
            self._board_kind == "preopen" or self._detail_return_stage == "preopen"
        )
        is_view_ticker = self._status_note == "view ticker" or (
            bool(self._ticker_job) and str(self._status_note or "").startswith("view ticker")
        )
        desk_code = self._broker_desk_code is not None
        is_broker_home = self._broker_page == "show" and desk_code
        is_broker_matrix = self._broker_page == "matrix" and desk_code
        is_broker_top = self._broker_page == "top" and desk_code
        is_broker_flow = self._broker_page == "flow" and desk_code
        is_broker_history = self._broker_page == "history" and desk_code
        is_broker_cal = self._broker_page == "cal" and desk_code

        def _hide_except(*keep: str) -> None:
            self._hide_judge_desk()
            self._hide_plan_desk()
            if "ticker" not in keep:
                self._hide_ticker_desk()
            if "broker" not in keep:
                self._hide_broker_desk()
            if "matrix" not in keep:
                self._hide_broker_matrix_desk()
            if "top" not in keep:
                self._hide_broker_top_desk()
            if "flow" not in keep:
                self._hide_broker_flow_desk()
            if "history" not in keep:
                self._hide_broker_history_desk()
            if "cal" not in keep:
                self._hide_broker_calendar_desk()
            if "preopen" not in keep:
                self._hide_preopen_inspect_desk()

        try:
            judge = self.query_one("#judge-desk", JudgeDesk)
        except Exception:
            judge = None
        try:
            ticker_desk = self.query_one("#ticker-desk", TickerDesk)
        except Exception:
            ticker_desk = None
        try:
            broker_desk = self.query_one("#broker-desk", BrokerDesk)
        except Exception:
            broker_desk = None
        try:
            matrix_desk = self.query_one("#broker-matrix-desk", BrokerMatrixDesk)
        except Exception:
            matrix_desk = None
        try:
            top_desk = self.query_one("#broker-top-desk", BrokerTopDesk)
        except Exception:
            top_desk = None
        try:
            flow_desk = self.query_one("#broker-flow-desk", BrokerFlowDesk)
        except Exception:
            flow_desk = None
        try:
            history_desk = self.query_one("#broker-history-desk", BrokerHistoryDesk)
        except Exception:
            history_desk = None
        try:
            calendar_desk = self.query_one("#broker-calendar-desk", BrokerCalendarDesk)
        except Exception:
            calendar_desk = None

        if is_judge and judge is not None:
            row = self._rows[self._row_index] if self._rows else None
            if row is not None and self._is_accum_row(row):
                model = self._build_judge_model(row)
                body.display = False
                _hide_except()
                judge.display = True
                judge.paint(
                    model,
                    detail_open=bool(getattr(self, "_judge_detail_open", False)),
                )
                self._detail_text = self._format_row_detail(
                    str(getattr(row, "ticker", self._focus_ticker)),
                    row,
                )
                return

        if is_preopen_inspect:
            row = self._rows[self._row_index] if self._rows else None
            if row is not None and self._is_preopen_row(row):
                from src.adapters.tui.preopen_inspect_model import (
                    build_preopen_inspect_model,
                )

                try:
                    poi = self.query_one("#preopen-inspect-desk", PreopenInspectDesk)
                except Exception:
                    poi = None
                if poi is not None:
                    model = build_preopen_inspect_model(
                        row,
                        rank=self._row_index + 1,
                        total=max(len(self._rows), 1),
                        snapshot_date=self._preopen_snapshot_date,
                        board_meta=str(getattr(self, "_meta", "") or ""),
                        warnings=tuple(self._preopen_warnings or ()),
                    )
                    body.display = False
                    _hide_except("preopen")
                    poi.display = True
                    poi.paint(
                        model,
                        detail_open=bool(getattr(self, "_preopen_detail_open", False)),
                    )
                    self._detail_text = self._format_row_detail(
                        str(getattr(row, "ticker", self._focus_ticker)),
                        row,
                    )
                    return

        if is_view_ticker and ticker_desk is not None:
            model = getattr(self, "_ticker_desk_model", None)
            if model is None:
                from src.adapters.tui.ticker_desk_model import (
                    build_ticker_desk_model_from_text,
                )

                model = build_ticker_desk_model_from_text(
                    ticker=str(self._focus_ticker or "—"),
                    body=self._detail_text or "",
                )
            body.display = False
            _hide_except("ticker")
            ticker_desk.display = True
            ticker_desk.paint(
                model,
                detail_open=bool(getattr(self, "_ticker_detail_open", False)),
            )
            # Re-apply job body after paint (chips stay; show panels hide)
            job_text = getattr(self, "_ticker_job_text", None)
            job = getattr(self, "_ticker_job", None)
            if job and job_text is not None and hasattr(ticker_desk, "set_job_view"):
                from src.adapters.shared.view_ticker_job_text import TickerJobText

                if isinstance(job_text, TickerJobText):
                    ticker_desk.set_job_view(
                        job,
                        title=job_text.title,
                        body=job_text.body,
                        desk=getattr(job_text, "desk", None),
                    )
            return

        if is_broker_home and broker_desk is not None:
            home_model = getattr(self, "_broker_desk_home_model", None)
            if home_model is None:
                from src.adapters.tui.broker_desk_home_model import (
                    build_broker_desk_home_model,
                )

                home_model = build_broker_desk_home_model(
                    None,
                    code=str(self._broker_desk_code or ""),
                    empty_reason="desk home model not loaded",
                )
            body.display = False
            _hide_except("broker")
            broker_desk.display = True
            broker_desk.paint(home_model)
            return

        if is_broker_matrix and matrix_desk is not None:
            mx_model = getattr(self, "_broker_desk_matrix_model", None)
            if mx_model is None:
                from src.adapters.tui.broker_desk_matrix_model import (
                    build_broker_desk_matrix_model,
                )

                mx_model = build_broker_desk_matrix_model(
                    None,
                    code=str(self._broker_desk_code or ""),
                    empty_reason="matrix model not loaded",
                )
            body.display = False
            _hide_except("matrix")
            matrix_desk.display = True
            matrix_desk.paint(mx_model)
            return

        if is_broker_top and top_desk is not None:
            top_model = getattr(self, "_broker_desk_top_model", None)
            if top_model is None:
                from src.adapters.tui.broker_desk_top_model import (
                    build_broker_desk_top_model,
                )

                top_model = build_broker_desk_top_model(
                    None,
                    code=str(self._broker_desk_code or ""),
                    empty_reason="top model not loaded",
                )
            body.display = False
            _hide_except("top")
            top_desk.display = True
            top_desk.paint(top_model)
            return

        if is_broker_flow and flow_desk is not None:
            flow_model = getattr(self, "_broker_desk_flow_model", None)
            if flow_model is None:
                from src.adapters.tui.broker_desk_flow_model import (
                    build_broker_desk_flow_model,
                )

                flow_model = build_broker_desk_flow_model(
                    None,
                    code=str(self._broker_desk_code or ""),
                    empty_reason="flow model not loaded",
                )
            body.display = False
            _hide_except("flow")
            flow_desk.display = True
            flow_desk.paint(flow_model)
            return

        if is_broker_history and history_desk is not None:
            hist_model = getattr(self, "_broker_desk_history_model", None)
            if hist_model is None:
                from src.adapters.tui.broker_desk_history_model import (
                    build_broker_desk_history_model,
                )

                hist_model = build_broker_desk_history_model(
                    None,
                    code=str(self._broker_desk_code or ""),
                    empty_reason="history model not loaded",
                )
            body.display = False
            _hide_except("history")
            history_desk.display = True
            history_desk.paint(hist_model)
            return

        if is_broker_cal and calendar_desk is not None:
            cal_model = getattr(self, "_broker_desk_calendar_model", None)
            if cal_model is None:
                from src.adapters.tui.broker_desk_calendar_model import (
                    build_broker_desk_calendar_model,
                )

                cal_model = build_broker_desk_calendar_model(
                    None,
                    code=str(self._broker_desk_code or ""),
                    empty_reason="calendar model not loaded",
                )
            body.display = False
            _hide_except("cal")
            calendar_desk.display = True
            calendar_desk.paint(cal_model)
            return

        body.display = True
        self._hide_instrument_desks()
        body.update(self._detail_text)

    def _paint_plan_stage(self, *, body: Static) -> None:
        """Plan stage: Geometry-mast widget; keep text body for scrapers/tests."""
        from src.adapters.tui.widgets.plan_desk import PlanDesk

        try:
            desk = self.query_one("#plan-desk", PlanDesk)
        except Exception:
            desk = None

        text = self._plan_body_text()
        if desk is not None:
            model = self._build_plan_model()
            body.display = False
            self._hide_judge_desk()
            desk.display = True
            desk.paint(model)
            return
        body.display = True
        self._hide_instrument_desks()
        body.update(text)

    def _build_plan_model(self) -> Any:
        from src.adapters.tui.plan_desk_model import build_plan_desk_model

        row = None
        if self._rows and 0 <= self._row_index < len(self._rows):
            row = self._rows[self._row_index]
        on_preopen = self._detail_return_stage == "preopen" or self._board_kind == "preopen"
        source = "Screen · pre-open" if on_preopen else "Screen · accumulation"
        return build_plan_desk_model(
            row,
            ticker=self._plan_ticker or self._focus_ticker,
            source=source,
            rank=self._row_index + 1,
            total=max(len(self._rows), 1),
            structure=self._plan_structure,
            result_line=self._plan_result,
            running=self._plan_running,
            paper_outcome=self._paper_outcome,
        )

    def _build_judge_model(self, row: Any) -> Any:
        from src.adapters.tui.judge_desk_model import build_judge_desk_model

        ticker = str(getattr(row, "ticker", self._focus_ticker) or "")
        seq_facts, seq_unavail = self._load_phase_sequence_for_judge(ticker, row)
        return build_judge_desk_model(
            row,
            rank=self._row_index + 1,
            total=max(len(self._rows), 1),
            board_summary=self._board_summary,
            effective_session=self._effective_session,
            market_context=self._market_context,
            phase_sequence=seq_facts,
            phase_sequence_unavailable=seq_unavail,
        )

    def _refresh_chrome(self) -> None:
        if self._stage != "detail" or self._status_note not in {"judge", "re-judging"}:
            self._invalidate_agent_turn()
        self.query_one("#view-title", Static).update(self._board_title)
        # Single-line meta only — multi-line + header height:auto zeroed the board table.
        meta_line = f"· {self._meta}"
        if self._stage == "accum" and self._board_summary:
            from src.adapters.tui.board_cell_markup import format_triage_markup

            triage = format_triage_markup(self._board_summary)
            if self._meta:
                meta_line = f"· {self._meta} · {triage}"
            else:
                meta_line = f"· {triage}"
        self.query_one("#view-meta", Static).update(meta_line)
        self.query_one("#mode-pill", Static).update(self._mode_label())
        self.query_one("#status", Static).update(self._status_text())
        self.query_one("#board-footer", Static).update(self._footer_hint())
        self.query_one("#side-mode", Static).update(f"Mode     {self._mode}")
        self._paint_cache_health_sidebar()
        self.query_one("#side-focus", Static).update(
            "none selected"
            if self._focus_ticker == "—"
            else f"{self._focus_ticker} · Enter judge · j re-judge · p plan"
        )
        self._paint_board_source_badge()

        body = self.query_one("#stage-body", Static)
        scroll = self.query_one("#stage-scroll", VerticalScroll)
        table = self.query_one("#board-table", DataTable)
        evidence = self.query_one("#evidence-strip", Static)

        if self._agent_stage_open:
            # Preserve OpenCode-style agent surface over normal stage paint.
            body.display = False
            table.display = False
            evidence.display = False
            scroll.display = True
            self._hide_instrument_desks()
            try:
                from src.adapters.tui.widgets.agent_commentary import AgentCommentary

                commentary = self.query_one("#agent-commentary", AgentCommentary)
                commentary.display = True
                commentary.set_stage_mode(True)
                self.query_one("#view-title", Static).update(
                    f"Agent · {str(self._focus_ticker or '—').upper()}"
                )
                self.query_one("#view-meta", Static).update(
                    "· non-authoritative · Esc leave · Enter send"
                )
                self.query_one("#board-footer", Static).update(
                    "Agent stage · deterministic Judge unchanged · Esc back · / re-focus"
                )
            except Exception:
                pass
            return

        if self._stage == "shell":
            scroll.display = True
            body.display = True
            self._hide_instrument_desks()
            body.update(self._shell_body())
            table.display = False
            evidence.display = False
        elif self._stage == "empty":
            # Session Cache is owned only by _paint_cache_health_sidebar above.
            # Do not hardcode "Cache empty" — board can be 0-candidate while local
            # candle/broker health is still ready/lag.
            scroll.display = True
            table.display = False
            evidence.display = False
            self._hide_instrument_desks()
            try:
                from src.adapters.tui.health_poster_model import build_health_poster_model
                from src.adapters.tui.widgets.health_poster_desk import HealthPosterDesk

                hp = self.query_one("#health-poster-desk", HealthPosterDesk)
                status = getattr(self._cache_health, "status", None)
                model = build_health_poster_model(
                    cache_status=str(status) if status else None,
                    board_title=self._board_title,
                    meta=self._meta,
                    board_kind=self._board_kind,
                    next_step=self._cache_next_step or "",
                )
                body.display = False
                hp.display = True
                hp.paint(model)
            except Exception:
                body.display = True
                body.update(self._empty_body())
        elif self._stage == "paper":
            scroll.display = True
            table.display = False
            evidence.display = False
            self._hide_instrument_desks()
            try:
                from src.adapters.tui.paper_desk_model import build_paper_desk_model
                from src.adapters.tui.widgets.paper_desk import PaperDesk

                desk = self.query_one("#paper-desk", PaperDesk)
                model = build_paper_desk_model(
                    self._paper_tape,
                    focus_ticker=self._focus_ticker,
                )
                body.display = False
                desk.display = True
                desk.paint(model)
            except Exception:
                body.display = True
                body.update(self._paper_outcome or "Paper · notebook")
        elif self._stage == "loading":
            from src.adapters.tui.chrome_cues import (
                loading_stage_body,
                should_keep_board_during_loading,
            )

            # Keep board ONLY for same-surface board recompute.
            # Instrument loads (ticker jobs, broker show/deep) must never unmask
            # the DataTable under a chip click (steals click → accidental Judge).
            keep_board = should_keep_board_during_loading(
                stage=self._stage,
                board_kind=str(self._board_kind or ""),
                status_note=self._status_note,
                board_title=self._board_title,
                has_rows=bool(self._rows),
            )
            if keep_board:
                scroll.display = False
                table.display = True
                if self._evidence_text:
                    evidence.display = True
                    evidence.update(self._evidence_text)
                else:
                    evidence.display = False
            else:
                scroll.display = True
                body.display = True
                self._hide_instrument_desks()
                body.update(
                    loading_stage_body(
                        board_title=self._board_title,
                        status_note=self._status_note,
                        stage=self._stage,
                    )
                )
                table.display = False
                evidence.display = False
        elif self._stage == "error":
            scroll.display = True
            body.display = True
            self._hide_instrument_desks()
            body.update(
                f"[#c97a72]Error[/]\n{self._error_text}\n\n[dim]r retry · Ctrl+P commands[/]"
            )
            table.display = False
            evidence.display = False
        elif self._stage == "detail":
            scroll.display = True
            table.display = False
            evidence.display = False
            self._paint_detail_stage(body=body, scroll=scroll)
            # Do not steal focus from chip bar / prompt (chip click consistency).
            self._focus_detail_scroll_if_safe(scroll)
        elif self._stage == "plan":
            scroll.display = True
            table.display = False
            evidence.display = False
            self._paint_plan_stage(body=body)
            self._focus_detail_scroll_if_safe(scroll)
        elif self._stage in {"broker-list", "ticker-desks"}:
            scroll.display = False
            table.display = True
            evidence.display = False
            self._hide_instrument_desks()
        elif self._stage in {"accum", "preopen"}:
            scroll.display = False
            table.display = True
            self._hide_instrument_desks()
            if self._evidence_text:
                evidence.display = True
                evidence.update(self._evidence_text)
            else:
                evidence.display = False

    # ── actions ────────────────────────────────────────────

    def action_command_palette(self) -> None:
        self._cancel_chord(silent=True)

        def _on_dismiss(command_id: str | None) -> None:
            if command_id:
                self._run_command(command_id)

        self.push_screen(CommandPalette(), _on_dismiss)

    # ── two-key chords (s a / s p / v t / v b) ─────────────

    def on_key(self, event: events.Key) -> None:
        """Prefix chords + desk-hub ``v`` + judge ``j`` re-judge (not list nav)."""
        if self._modal_blocks_board_keys():
            return

        key = event.key
        if key == "escape" and self._chord_prefix is not None:
            event.prevent_default()
            event.stop()
            self._cancel_chord(silent=False)
            return

        if self._chord_prefix is not None:
            event.prevent_default()
            event.stop()
            prefix = self._chord_prefix
            self._clear_chord_state()
            self._resolve_chord(prefix, key)
            return

        # Judge only: ``j`` re-judges. Never list navigation (arrows own ↑↓).
        if (
            key == "j"
            and self._stage == "detail"
            and self._status_note
            in {
                "judge",
                "re-judging",
            }
        ):
            event.prevent_default()
            event.stop()
            self.action_rejudge_ticker()
            return

        # Plan stage: ``l`` = explicit paper notebook log (confirm first).
        if key == "l" and self._stage == "plan":
            event.prevent_default()
            event.stop()
            self.action_paper_log()
            return

        if key == "s":
            event.prevent_default()
            event.stop()
            self._begin_chord("s")
            return

        if key == "v":
            event.prevent_default()
            event.stop()
            if self._desk_hub_active():
                # Single-key: desk → top stock (CLI parity trail)
                self.action_broker_jump_ticker()
            else:
                self._begin_chord("v")
            return

    def _begin_chord(self, prefix: str) -> None:
        self._clear_chord_state()
        self._chord_prefix = prefix
        hint = self._CHORD_HINTS.get(prefix, prefix)
        self.notify(hint, timeout=self._CHORD_TIMEOUT_S)
        self._chord_timer = self.set_timer(
            self._CHORD_TIMEOUT_S,
            self._on_chord_timeout,
            name=f"chord-{prefix}",
        )

    def _on_chord_timeout(self) -> None:
        if self._chord_prefix is not None:
            prefix = self._chord_prefix
            self._clear_chord_state()
            self.notify(f"{prefix}… cancelled", timeout=0.8)

    def _cancel_chord(self, *, silent: bool) -> None:
        if self._chord_prefix is None:
            return
        prefix = self._chord_prefix
        self._clear_chord_state()
        if not silent:
            self.notify(f"{prefix}… cancelled", timeout=0.8)

    def _clear_chord_state(self) -> None:
        if self._chord_timer is not None:
            self._chord_timer.stop()
            self._chord_timer = None
        self._chord_prefix = None

    def _resolve_chord(self, prefix: str, key: str) -> None:
        # Character keys arrive as "a"/"t"; ignore modifiers.
        cmd = self._CHORD_MAP.get((prefix, key))
        if cmd is None:
            self.notify(f"Unknown · {prefix} {key}", timeout=1.0)
            return
        self._run_command(cmd)

    def action_toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self.query_one("#sidebar").set_class(not self._sidebar_visible, "hidden")
        self.notify(
            "Sidebar hidden" if not self._sidebar_visible else "Sidebar shown",
            timeout=1.2,
        )

    def action_show_help(self) -> None:
        self.push_screen(HelpModal())

    def action_quit(self) -> None:
        self.workers.cancel_all()
        self.exit()

    def action_go_back(self) -> None:
        if self._modal_blocks_board_keys():
            return
        if self._agent_stage_open:
            self._agent_generation += 1
            self._agent_loading = False
            self._exit_agent_stage(refresh=True)
            return
        self._invalidate_agent_turn()
        if self._stage == "ticker-desks":
            # Back to view ticker for the stock (preserve board return stage).
            stock = self._ticker_desks_stock
            if not stock:
                self._stage = "shell"
                self._board_kind = "none"
                self._clear_broker_axis()
                self._ticker_desks_stock = None
                self._refresh_chrome()
                return
            self._focus_ticker = stock
            self._ticker_desks_stock = None
            self._desk_entry = None
            self._broker_page = None
            self._broker_desk_code = None
            self._open_view_ticker_dashboard(from_desk=False, preserve_return=True)
            return
        if self._stage == "broker-list":
            self._clear_broker_axis()
            target = self._broker_list_return
            if target in {"accum", "preopen"} and self._rows:
                self._stage = target
                self._board_kind = target  # type: ignore[assignment]
            else:
                self._stage = "shell"
                self._board_kind = "none"
            self._refresh_chrome()
            if self._stage in {"accum", "preopen"}:
                self._render_board_table()
                if self._stage == "preopen":
                    self._update_preopen_evidence()
                else:
                    self._update_accum_evidence()
            return
        if self._stage in {"detail", "plan"}:
            # Ticker job (flow/foreign/dist/fin) → show first
            if self._stage == "detail" and self._ticker_job:
                self._close_ticker_job()
                return
            # Desk trail: deep → show → list or ticker-desks.
            if self._stage == "detail" and self._broker_page in {
                "top",
                "flow",
                "history",
                "matrix",
                "cal",
            }:
                if self._broker_desk_code:
                    self._open_broker_desk_show(
                        code=self._broker_desk_code,
                        entry=self._desk_entry,
                    )
                    return
            if self._stage == "detail" and self._broker_page == "show":
                self._view_from_desk = False
                # From brokers chip job → back to on-ticker brokers job (not independent stage)
                if self._desk_entry == "ticker-brokers-job" and self._ticker_desks_stock:
                    stock = str(self._ticker_desks_stock).upper()
                    self._broker_page = None
                    self._broker_desk_code = None
                    self._focus_ticker = stock
                    self._open_ticker_job("brokers", stock)
                    return
                if self._desk_entry == "ticker-desks" and self._ticker_desks_stock:
                    self._restore_ticker_desks_table()
                    return
                self._broker_page = "list"
                self._stage = "broker-list"
                self._plan_running = False
                self._refresh_chrome()
                self._render_board_table()
                self.query_one("#board-table", DataTable).focus()
                return
            if self._stage == "detail" and self._view_from_desk and self._broker_desk_code:
                # View ticker opened via desk ``v`` → back to desk home
                self._view_from_desk = False
                self._open_broker_desk_show(
                    code=self._broker_desk_code,
                    entry=self._desk_entry,
                )
                return
            # Explicit return stage — never infer only from detail title.
            target = self._detail_return_stage
            if target == "broker-list" and self._broker_rows:
                self._stage = "broker-list"
                self._broker_page = "list"
                self._plan_running = False
                self._refresh_chrome()
                self._render_board_table()
                return
            if target in {"accum", "preopen"} and self._rows:
                self._stage = target
                self._board_kind = target  # type: ignore[assignment]
                self._clear_broker_axis()
                self._ticker_desks_stock = None
            elif self._rows and self._board_kind in {"accum", "preopen"}:
                self._stage = self._board_kind
                self._clear_broker_axis()
                self._ticker_desks_stock = None
            else:
                self._stage = "shell"
                self._board_kind = "none"
                self._clear_broker_axis()
                self._ticker_desks_stock = None
            self._plan_running = False
            self._refresh_chrome()
            if self._stage in {"accum", "preopen"}:
                self._render_board_table()
                if self._stage == "preopen":
                    self._update_preopen_evidence()
                else:
                    self._update_accum_evidence()

    def _clear_broker_axis(self) -> None:
        self._broker_desk_code = None
        self._broker_page = None
        self._broker_jump_ticker = None
        self._view_from_desk = False
        self._desk_entry = None
        # _ticker_desks_stock cleared by callers leaving the stock→desk trail

    def _desk_hub_active(self) -> bool:
        return (
            self._broker_desk_code is not None
            and self._stage == "detail"
            and self._broker_page in {"show", "top", "flow", "history", "matrix", "cal"}
        )

    def action_broker_top(self) -> None:
        if self._modal_blocks_board_keys() or not self._desk_hub_active():
            return
        self._open_broker_deep("top")

    def _on_ticker_show_or_job(self) -> bool:
        """True on ticker show or stock-axis job (brokers/flow/foreign/dist/fin)."""
        if self._stage not in {"detail", "loading"}:
            return False
        if self._ticker_job is not None:
            return True
        note = str(self._status_note or "")
        if note == "view ticker" or note == "loading ticker job":
            return True
        # view ticker brokers|flow|… — not independent ticker-desks stage
        if note.startswith("view ticker ") and "desks" not in note:
            return True
        return False

    def action_broker_flow(self) -> None:
        """Desk hub ``f`` or ticker show/job ``f`` → flow job (stage-local)."""
        if self._modal_blocks_board_keys():
            return
        if self._on_ticker_show_or_job():
            self.action_ticker_job("flow")
            return
        if not self._desk_hub_active():
            return
        self._open_broker_deep("flow")

    def action_broker_history(self) -> None:
        if self._modal_blocks_board_keys() or not self._desk_hub_active():
            return
        self._open_broker_deep("history")

    def action_broker_matrix(self) -> None:
        if self._modal_blocks_board_keys() or not self._desk_hub_active():
            return
        self._open_broker_deep("matrix")

    def action_broker_calendar(self) -> None:
        if self._modal_blocks_board_keys() or not self._desk_hub_active():
            return
        self._open_broker_deep("cal")

    def action_broker_jump_ticker(self) -> None:
        if self._modal_blocks_board_keys() or not self._desk_hub_active():
            return
        stock = self._broker_jump_ticker
        if not stock:
            self.notify("No top stock on this desk to open", timeout=1.5)
            return
        self._focus_ticker = stock
        self._view_from_desk = True
        self._open_view_ticker_dashboard(from_desk=True)

    def action_toggle_detail(self) -> None:
        """Shared ``d``: brief ↔ detail on Judge + Ticker show (Chip bar contract)."""
        if self._modal_blocks_board_keys():
            return
        if self._stage != "detail":
            return
        if self._status_note == "view ticker" or (
            self._ticker_job and str(self._status_note or "").startswith("view ticker")
        ):
            # Density only when show is front (not job sub-stage)
            if self._ticker_job:
                return
            self._ticker_detail_open = not bool(getattr(self, "_ticker_detail_open", False))
            # Density = [d] is-on only — no brief/detail meta noise
            self._meta = "from desk" if self._view_from_desk else "local cache"
            self._refresh_chrome()
            on = "on" if self._ticker_detail_open else "off"
            self.notify(f"Ticker · detail {on}", timeout=1.2)
            return
        if self._status_note in {"judge", "re-judging"}:
            self._judge_detail_open = not bool(getattr(self, "_judge_detail_open", False))
            self._meta = "j re-judge · local"
            self._refresh_chrome()
            on = "on" if self._judge_detail_open else "off"
            self.notify(f"Judge · detail {on}", timeout=1.2)
            return
        if self._status_note == "inspect" and (
            self._board_kind == "preopen" or self._detail_return_stage == "preopen"
        ):
            # Pre-open: d still expands optional panels (no density chip on bar)
            self._preopen_detail_open = not bool(getattr(self, "_preopen_detail_open", False))
            self._meta = "d toggle · local"
            self._refresh_chrome()
            on = "on" if self._preopen_detail_open else "off"
            self.notify(f"Pre-open · detail {on}", timeout=1.2)
            return

    def action_ticker_job(self, job: str) -> None:
        """Ticker job chips / power keys · sibling CLI verbs (browse only)."""
        if self._modal_blocks_board_keys():
            return
        # Allow open when show or already on a ticker job (switch jobs)
        if not self._on_ticker_show_or_job():
            return
        job = (job or "").strip().lower()
        # All stock-axis jobs stay on ticker chip shell (including brokers)
        if job not in {"brokers", "flow", "foreign", "dist", "fin"}:
            return
        # Second press same job → close to show
        if self._ticker_job == job:
            self._close_ticker_job()
            return
        # Company ticker for load — not a desk code from brokers radar selection
        stock = str(getattr(self, "_ticker_desks_stock", None) or self._focus_ticker or "").upper()
        if not stock or stock == "—":
            self.notify("No ticker focused", timeout=1.5)
            return
        self._open_ticker_job(job, stock)

    def action_ticker_job_brokers(self) -> None:
        """Power ``b`` · brokers chip — on-ticker job (not independent stage)."""
        self.action_ticker_job("brokers")

    def _focus_detail_scroll_if_safe(self, scroll: VerticalScroll) -> None:
        """Focus scroll for page keys only when focus is not on chips/prompt."""
        try:
            focused = self.focused
        except Exception:
            focused = None
        if focused is not None:
            # Chip bar / FlagChip / prompt input: leave focus where operator put it
            try:
                from src.adapters.tui.widgets.flag_chip import FlagChip

                if isinstance(focused, FlagChip):
                    return
            except Exception:
                pass
            fid = getattr(focused, "id", None) or ""
            if fid in {"prompt-input", "prompt-rail"}:
                return
            # Any descendant of a ChipBar — keep chip toolbar focus
            try:
                from src.adapters.tui.widgets.chip_bar import ChipBar

                node = focused
                for _ in range(8):
                    parent = getattr(node, "parent", None)
                    if parent is None:
                        break
                    if isinstance(parent, ChipBar):
                        return
                    node = parent
            except Exception:
                pass
        try:
            scroll.focus()
        except Exception:
            pass

    def _open_ticker_job(self, job: str, stock: str) -> None:
        """Load job under chip bar — quiet in-place (no plain-text loading dump).

        Design: chip is-on immediately · hold show/prior body until structured
        payload ready · meta may say loading · never unmask board under click.
        """
        self._ticker_job = job
        # Drop stale desk so chrome cannot re-apply the previous job under new chip
        self._ticker_job_text = None
        # Stay on detail instrument — never global loading+keep_board (chip click safe)
        self._stage = "detail"
        self._board_title = f"View · ticker · {stock} · {job}"
        self._meta = f"{job} · loading · local cache"
        self._status_note = f"view ticker {job}"
        try:
            desk = self.query_one("#ticker-desk")
            if hasattr(desk, "set_job_view"):
                # Pending: job chip is-on, empty body/desk → hold show surface (no essay)
                desk.set_job_view(  # type: ignore[attr-defined]
                    job,
                    title=f"View · ticker · {stock} · {job}",
                    body="",
                    desk=None,
                )
        except Exception:
            pass
        self._refresh_chrome()
        self._execute_ticker_job(job, stock)

    def _close_ticker_job(self) -> None:
        """Trail: job → ticker show (density preserved)."""
        # Prefer company stock (brokers job may have moved focus to a desk code)
        stock = str(getattr(self, "_ticker_desks_stock", None) or self._focus_ticker or "").upper()
        if self._ticker_job == "brokers":
            self._broker_rows = []
            self._broker_row_index = 0
            self._desk_entry = None
            # restore company ticker for show
            if getattr(self, "_ticker_desks_stock", None):
                stock = str(self._ticker_desks_stock).upper()
                self._focus_ticker = stock
            self._ticker_desks_stock = None
        self._ticker_job = None
        self._ticker_job_text = None
        self._stage = "detail"
        self._status_note = "view ticker"
        self._meta = "from desk" if self._view_from_desk else "local cache"
        self._board_title = f"View · ticker · {stock}"
        try:
            desk = self.query_one("#ticker-desk")
            if hasattr(desk, "set_job_view"):
                desk.set_job_view(None)  # type: ignore[attr-defined]
            elif hasattr(desk, "set_active_job"):
                desk.set_active_job(None)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._refresh_chrome()

    @work(thread=True, exclusive=True, group="detail")
    def _execute_ticker_job(self, job: str, stock: str) -> None:
        try:
            if self._ticker_job_loader is not None:
                fin_period = str(getattr(self, "_ticker_fin_period", "quarterly") or "quarterly")
                try:
                    payload = self._ticker_job_loader(job, stock, fin_period)
                except TypeError:
                    # Older test/injected loaders: (job, ticker) only
                    payload = self._ticker_job_loader(job, stock)
            else:
                from src.adapters.shared.view_ticker_job_text import empty_ticker_job

                payload = empty_ticker_job(job, stock, message="no ticker job loader")
            dispatch_if_active(self, self._on_ticker_job_ready, job, stock, payload)
        except Exception as exc:
            dispatch_if_active(self, self._on_board_error, f"view ticker {job}: {exc}")

    def _on_ticker_job_ready(self, job: str, stock: str, payload: Any) -> None:
        from src.adapters.shared.view_ticker_job_text import TickerJobText, empty_ticker_job

        if not isinstance(payload, TickerJobText):
            payload = empty_ticker_job(job, stock, message="invalid job payload")
        self._ticker_job = job
        self._ticker_job_text = payload
        self._detail_text = payload.as_text()
        self._stage = "detail"
        self._board_title = payload.title
        self._meta = f"{payload.cli_verb} · local cache"
        self._status_note = f"view ticker {job}"
        # Keep company ticker for job identity (not desk code)
        self._focus_ticker = stock
        if job == "brokers":
            # Rows for ↑↓ · Enter desk home — still under ticker chips
            rows = list(getattr(payload, "broker_rows", ()) or ())
            self._broker_rows = rows
            self._broker_row_index = 0
            self._ticker_desks_stock = stock
            self._desk_entry = "ticker-brokers-job"
            self._broker_page = None
            self._broker_desk_code = None
        try:
            desk = self.query_one("#ticker-desk")
            if hasattr(desk, "set_job_view"):
                desk.set_job_view(  # type: ignore[attr-defined]
                    job,
                    title=payload.title,
                    body=payload.body,
                    desk=getattr(payload, "desk", None),
                )
            elif hasattr(desk, "set_active_job"):
                desk.set_active_job(job)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._refresh_chrome()
        # Quiet load — chip is-on + body are the feedback (no toast spam)

    def action_ticker_job_foreign(self) -> None:
        self.action_ticker_job("foreign")

    def action_ticker_job_dist(self) -> None:
        self.action_ticker_job("dist")

    def action_ticker_job_fin(self) -> None:
        self.action_ticker_job("fin")

    def action_toggle_fin_period(self) -> None:
        """Binary toggle ``y``: fin period quarterly ↔ annual (CLI --period).

        Armed only while the fin job surface is front. Flip label + reload via
        use-case period_type — no adapter-side fetch policy.
        """
        if self._modal_blocks_board_keys():
            return
        if not self._on_ticker_show_or_job():
            return
        if self._ticker_job != "fin":
            return
        cur = (getattr(self, "_ticker_fin_period", None) or "quarterly").strip().lower()
        self._ticker_fin_period = "annual" if cur != "annual" else "quarterly"
        stock = str(getattr(self, "_ticker_desks_stock", None) or self._focus_ticker or "").upper()
        if not stock or stock == "—":
            self.notify("No ticker focused", timeout=1.5)
            return
        # Reload fin in place (do not use action_ticker_job — second press closes)
        self._open_ticker_job("fin", stock)
        grain = self._ticker_fin_period
        self.notify(f"Fin · {grain} · CLI --period {grain}", timeout=1.2)

    def action_focus_prompt(self) -> None:
        """Focus prompt rail without forcing agent stage (:)."""
        if self._modal_blocks_board_keys():
            return
        try:
            rail = self.query_one("#prompt-rail", Vertical)
            rail.add_class("is-focus")
            inp = self.query_one("#prompt-input", Input)
            inp.placeholder = "ask agent · Enter sends · mode cli for CLI (not wired)"
            inp.focus()
        except Exception:
            return

    def action_focus_agent(self) -> None:
        """/ — enter agent mode and OpenCode-style stage replace when Judge is open."""
        if self._modal_blocks_board_keys():
            return
        self._set_prompt_mode_chip("agent")
        on_judge = self._stage == "detail" and self._status_note in {
            "judge",
            "re-judging",
        }
        if on_judge:
            self._enter_agent_stage(ready=True)
        else:
            self.notify(
                "Open accumulation Judge (Enter on a row) then / to ask",
                timeout=2.2,
            )
        try:
            rail = self.query_one("#prompt-rail", Vertical)
            rail.add_class("is-focus")
            inp = self.query_one("#prompt-input", Input)
            inp.placeholder = "ask about this Judge · Enter send · Esc leave agent"
            inp.focus()
        except Exception:
            return

    def _set_prompt_mode_chip(self, mode: str) -> None:
        mode = (mode or "idle").lower()
        if mode not in {"idle", "agent", "cli"}:
            mode = "idle"
        self._prompt_mode = mode
        try:
            chip = self.query_one("#prompt-mode", Static)
            chip.update(mode)
            chip.remove_class("is-agent", "is-cli")
            if mode == "agent":
                chip.add_class("is-agent")
            elif mode == "cli":
                chip.add_class("is-cli")
            sub = self.query_one("#prompt-sub", Static)
            remote = "remote" if self._agent_provider_available else "unavailable"
            if mode == "agent":
                sub.update(f"· {remote} · {self._agent_provider}")
            elif mode == "cli":
                sub.update("· cli path · not wired yet")
            else:
                sub.update("· local · / agent · : prompt")
        except Exception:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Submit agent turn; free text auto-enters agent mode (not silent idle)."""
        if event.input.id != "prompt-input":
            return
        text = (event.value or "").strip()
        event.input.value = ""
        low = text.lower()
        if low in {"mode idle", "idle"}:
            self._exit_agent_stage(refresh=True)
            self._set_prompt_mode_chip("idle")
            self.notify("prompt · mode idle", timeout=1.2)
            return
        if low in {"mode agent", "agent"}:
            self.action_focus_agent()
            return
        if low in {"mode cli", "cli"}:
            self._exit_agent_stage(refresh=True)
            self._set_prompt_mode_chip("cli")
            self.notify("prompt · cli · not wired yet", timeout=1.5)
            return
        if low in {"/reset", "session reset", "reset session"}:
            self._reset_agent_session()
            return
        if text and self._prompt_mode == "cli":
            self.notify("prompt · cli · not wired yet", timeout=1.5)
            return
        if text:
            # Auto-enter agent mode for any real question (no silent drop).
            self._set_prompt_mode_chip("agent")
            self._submit_agent_turn(text)
            return
        try:
            rail = self.query_one("#prompt-rail", Vertical)
            rail.remove_class("is-focus")
            if not self._agent_stage_open:
                table = self.query_one("#board-table", DataTable)
                if table.display:
                    table.focus()
            else:
                self.query_one("#prompt-input", Input).focus()
        except Exception:
            pass

    def _reset_agent_session(self) -> None:
        """Clear process-local agent session state (ADR-063)."""
        runner = self._agent_turn_runner
        reset = getattr(runner, "reset_session", None)
        if not callable(reset):
            self.notify("Agent session reset unavailable", timeout=1.5)
            return
        try:
            session_id = reset()
        except Exception:
            self.notify("Agent session reset failed", timeout=1.5)
            return
        self._invalidate_agent_turn()
        self.notify(f"Agent session reset · {session_id}", timeout=1.8)

    def _submit_agent_turn(self, user_text: str) -> None:
        from src.application.dto.accumulation_agent import AgentTurnRequest

        if self._stage != "detail" or self._status_note not in {"judge", "re-judging"}:
            self.notify(
                "Agent is available only in accumulation Judge · Enter a row first",
                timeout=2.2,
            )
            return
        row = self._rows[self._row_index] if self._rows else None
        source = getattr(row, "source", None)
        if source is None:
            self._show_agent_unavailable("Full Judge context required · press j to re-judge")
            return
        if self._agent_turn_runner is None:
            self._show_agent_unavailable(
                "Agent commentary is unavailable · check ai.enabled and API key"
            )
            return
        # Cancel in-flight without collapsing stage if we are already in agent stage.
        keep_stage = self._agent_stage_open
        self._agent_generation += 1
        self._agent_loading = False
        if not keep_stage:
            try:
                self.query_one("#agent-commentary").clear()
            except Exception:
                pass
        generation = self._agent_generation
        ticker = str(self._focus_ticker).upper()
        stage_id = (self._stage, self._status_note)
        self._agent_loading = True
        self._agent_last_question = user_text
        self._set_prompt_mode_chip("agent")
        if not self._agent_stage_open:
            self._enter_agent_stage(ready=False)
        commentary = self.query_one("#agent-commentary")
        commentary.set_stage_mode(True)
        commentary.show_loading(
            provider=self._agent_provider,
            ticker=ticker,
            question=user_text,
        )
        try:
            sub = self.query_one("#prompt-sub", Static)
            remote = "remote" if self._agent_provider_available else "unavailable"
            sub.update(f"· {remote} · {self._agent_provider}")
            rail = self.query_one("#prompt-rail", Vertical)
            rail.add_class("is-focus")
            self.query_one("#prompt-input", Input).focus()
        except Exception:
            pass
        self._execute_agent_turn(
            generation,
            stage_id,
            ticker,
            source,
            AgentTurnRequest(user_text=user_text, candidate=source),
        )

    def _show_agent_unavailable(self, message: str) -> None:
        from src.application.dto.accumulation_agent import (
            AgentTurnResult,
            AgentTurnStatus,
        )

        self._agent_generation += 1
        self._agent_loading = False
        if not self._agent_stage_open:
            self._enter_agent_stage(ready=False)
        row = self._rows[self._row_index] if self._rows else None
        source = getattr(row, "source", None)
        as_of = str(getattr(getattr(source, "trade_setup", None), "snapshot_date", "—"))
        commentary = self.query_one("#agent-commentary")
        commentary.set_stage_mode(True)
        commentary.show_result(
            AgentTurnResult(status=AgentTurnStatus.UNAVAILABLE, error_message=message),
            as_of=as_of,
            question=self._agent_last_question,
            ticker=str(self._focus_ticker or "—").upper(),
        )

    @work(thread=True, group="agent")
    def _execute_agent_turn(
        self,
        generation: int,
        stage_id: tuple[str, str],
        ticker: str,
        source: Any,
        request: Any,
    ) -> None:
        assert self._agent_turn_runner is not None

        def _progress(message: str) -> None:
            dispatch_if_active(
                self,
                self._on_agent_progress,
                generation,
                stage_id,
                ticker,
                message,
            )

        def _approval(req: Any) -> bool:
            # Sync confirm from worker: block until UI posts decision.
            import threading

            box: dict[str, bool | None] = {"ok": None}
            done = threading.Event()

            def _ask() -> None:
                try:
                    self._ask_elevated_tool_confirm(req, box, done)
                except Exception:
                    box["ok"] = False
                    done.set()

            try:
                self.call_from_thread(_ask)
            except Exception:
                box["ok"] = False
                done.set()
            done.wait(timeout=120.0)
            return bool(box["ok"])

        try:
            runner = self._agent_turn_runner
            try:
                result = runner(request, on_progress=_progress, on_approval=_approval)
            except TypeError:
                try:
                    result = runner(request, on_progress=_progress)
                except TypeError:
                    result = runner(request)
        except Exception:
            from src.application.dto.accumulation_agent import (
                AgentTurnResult,
                AgentTurnStatus,
            )

            result = AgentTurnResult(
                status=AgentTurnStatus.FAILED,
                error_message="Agent commentary failed unexpectedly",
            )
        dispatch_if_active(
            self,
            self._on_agent_turn_done,
            generation,
            stage_id,
            ticker,
            source,
            result,
        )

    def _on_agent_progress(
        self,
        generation: int,
        stage_id: tuple[str, str],
        ticker: str,
        message: str,
    ) -> None:
        """Paint multi-round progress only for the active Research Cockpit turn."""
        if generation != self._agent_generation:
            return
        if (self._stage, self._status_note) != stage_id:
            return
        if str(self._focus_ticker).upper() != ticker:
            return
        try:
            commentary = self.query_one("#agent-commentary")
            commentary.show_progress(
                message,
                provider=self._agent_provider,
                ticker=ticker,
            )
        except Exception:
            pass

    def _ask_elevated_tool_confirm(self, req: Any, box: dict, done: Any) -> None:
        """Light y/n confirm (default Yes). Free-text chat is not authorization."""
        from textual.containers import Horizontal, Vertical
        from textual.screen import ModalScreen
        from textual.widgets import Button, Static

        tool = str(getattr(req, "tool_name", "tool"))
        summary = str(getattr(req, "arg_summary", ""))
        implication = str(getattr(req, "implication", ""))

        class _Confirm(ModalScreen[bool]):
            def compose(self):  # type: ignore[no-untyped-def]
                with Vertical(id="agent-confirm"):
                    yield Static("AI Research Cockpit · confirm", classes="title")
                    yield Static(f"Tool: {tool}")
                    yield Static(f"Args: {summary}")
                    yield Static(implication)
                    with Horizontal():
                        yield Button("Yes", id="yes", variant="success")
                        yield Button("No", id="no", variant="error")

            def on_mount(self) -> None:
                try:
                    self.query_one("#yes", Button).focus()
                except Exception:
                    pass

            def on_button_pressed(self, event: Button.Pressed) -> None:
                self.dismiss(event.button.id == "yes")

        def _done(result: bool | None) -> None:
            box["ok"] = bool(result)
            done.set()

        self.push_screen(_Confirm(), _done)

    def _remember_agent_success(
        self, result: Any, *, as_of: str, ticker: str, question: str
    ) -> None:
        if getattr(result, "status", None) is None:
            return
        from src.application.dto.accumulation_agent import AgentTurnStatus

        if result.status not in {AgentTurnStatus.SUCCESS, AgentTurnStatus.PARTIAL}:
            return
        self._agent_last_good = {
            "result": result,
            "as_of": as_of,
            "ticker": ticker,
            "question": question,
        }

    def _restore_agent_last_good(self, *, error: str) -> bool:
        snap = getattr(self, "_agent_last_good", None)
        if not snap:
            return False
        try:
            commentary = self.query_one("#agent-commentary")
            commentary.show_result(
                snap["result"],
                as_of=snap["as_of"],
                question=snap.get("question") or "",
                ticker=snap.get("ticker") or "—",
            )
            commentary.query_one(".agent-error").update(error)
            return True
        except Exception:
            return False

    def _on_agent_turn_done(
        self,
        generation: int,
        stage_id: tuple[str, str],
        ticker: str,
        source: Any,
        result: Any,
    ) -> None:
        row = self._rows[self._row_index] if self._rows else None
        if generation != self._agent_generation:
            return
        if (self._stage, self._status_note) != stage_id:
            return
        if str(self._focus_ticker).upper() != ticker:
            return
        if getattr(row, "source", None) is not source:
            return
        self._agent_loading = False
        as_of = str(getattr(source.trade_setup, "snapshot_date", "—"))
        if not self._agent_stage_open:
            self._enter_agent_stage(ready=False)
        commentary = self.query_one("#agent-commentary")
        commentary.set_stage_mode(True)
        from src.application.dto.accumulation_agent import AgentTurnStatus

        status = getattr(result, "status", None)
        if status in {AgentTurnStatus.FAILED, AgentTurnStatus.CANCELLED} and getattr(
            result, "restore_last_good", False
        ):
            if self._restore_agent_last_good(
                error=str(getattr(result, "error_message", None) or "turn failed")
            ):
                return
        commentary.show_result(
            result,
            as_of=as_of,
            question=self._agent_last_question,
            ticker=ticker,
        )
        self._remember_agent_success(
            result,
            as_of=as_of,
            ticker=ticker,
            question=self._agent_last_question,
        )

    def on_input_blurred(self, event: Input.Blurred) -> None:
        if getattr(event.input, "id", None) != "prompt-input":
            return
        try:
            self.query_one("#prompt-rail", Vertical).remove_class("is-focus")
        except Exception:
            pass

    def action_ticker_desks(self) -> None:
        """Alias: brokers chip path — on-ticker job (consistent with flow/foreign/…)."""
        self.action_ticker_job("brokers")

    def action_refresh_local(self) -> None:
        if self._modal_blocks_board_keys():
            return
        self._invalidate_agent_turn()
        # Prefer board_kind over title heuristics (detail titles include ticker).
        kind = self._board_kind
        if self._stage == "detail":
            kind = self._detail_return_stage if self._detail_return_stage != "shell" else kind
        if kind == "preopen" or self._stage == "preopen":
            self._run_command("screen-preopen")
        elif kind == "accum" or self._stage in {"accum", "error"}:
            self._run_command("screen-accum")
        elif self._board_title.startswith("Screen · accumulation"):
            self._run_command("screen-accum")
        else:
            self.notify("Nothing to refresh — open a screen via Ctrl+P", timeout=1.5)

    def action_plan_swing(self) -> None:
        if self._modal_blocks_board_keys():
            return
        self._run_command("plan-swing")

    def action_view_ticker(self) -> None:
        """Enter: board inspect, desk home from list/desks, or desk from brokers job."""
        if self._modal_blocks_board_keys():
            return
        if self._stage == "broker-list":
            self._open_broker_desk_show(entry="broker-list")
            return
        if self._stage == "ticker-desks":
            self._open_broker_desk_show(entry="ticker-desks")
            return
        # On-ticker brokers job · same Enter → desk home as radar stage
        if self._stage == "detail" and self._ticker_job == "brokers" and self._broker_rows:
            self._open_broker_desk_show(entry="ticker-brokers-job")
            return
        self._open_detail()

    def _modal_blocks_board_keys(self) -> bool:
        """True when a modal (palette/confirm/help) is on top — do not steal keys."""
        # screen_stack[0] is the main CockpitApp screen; anything above is a modal.
        return len(self.screen_stack) > 1

    def _brokers_job_active(self) -> bool:
        return self._stage == "detail" and self._ticker_job == "brokers" and bool(self._broker_rows)

    def _move_brokers_job_cursor(self, *, delta: int) -> None:
        """↑↓ on brokers chip job — reselect row and repaint radar highlight."""
        if not self._broker_rows:
            return
        n = len(self._broker_rows)
        self._broker_row_index = max(0, min(n - 1, self._broker_row_index + delta))
        self._update_broker_focus()
        # Repaint job body with selection mark
        payload = self._ticker_job_text
        if payload is None:
            return
        from src.adapters.shared.view_ticker_job_text import format_ticker_brokers_job

        stock = str(self._ticker_desks_stock or self._focus_ticker or "").upper()
        desk_model = getattr(payload, "desk", None)
        rebuilt = format_ticker_brokers_job(
            stock,
            self._broker_rows,
            as_of=getattr(desk_model, "as_of", None) if desk_model else None,
            note=getattr(desk_model, "note", None) if desk_model else None,
            selected_index=self._broker_row_index,
            fetch_hint=getattr(payload, "fetch_hint", None),
        )
        self._ticker_job_text = rebuilt
        try:
            desk = self.query_one("#ticker-desk")
            if hasattr(desk, "set_job_view"):
                desk.set_job_view(  # type: ignore[attr-defined]
                    "brokers",
                    title=rebuilt.title,
                    body=rebuilt.body,
                    desk=rebuilt.desk,
                )
        except Exception:
            pass

    def action_cursor_down(self) -> None:
        if self._modal_blocks_board_keys():
            return
        if self._brokers_job_active():
            self._move_brokers_job_cursor(delta=1)
            return
        if self._stage in {"broker-list", "ticker-desks"}:
            if not self._broker_rows:
                return
            self._broker_row_index = min(len(self._broker_rows) - 1, self._broker_row_index + 1)
            self._sync_table_cursor()
            self._update_broker_focus()
            return
        if self._stage not in {"accum", "preopen"} or not self._rows:
            return
        self._invalidate_agent_turn()
        self._row_index = min(len(self._rows) - 1, self._row_index + 1)
        self._sync_table_cursor()
        self._update_focus_from_row()

    def action_cursor_up(self) -> None:
        if self._modal_blocks_board_keys():
            return
        if self._brokers_job_active():
            self._move_brokers_job_cursor(delta=-1)
            return
        if self._stage in {"broker-list", "ticker-desks"}:
            if not self._broker_rows:
                return
            self._broker_row_index = max(0, self._broker_row_index - 1)
            self._sync_table_cursor()
            self._update_broker_focus()
            return
        if self._stage not in {"accum", "preopen"} or not self._rows:
            return
        self._invalidate_agent_turn()
        self._row_index = max(0, self._row_index - 1)
        self._sync_table_cursor()
        self._update_focus_from_row()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.cursor_row is None or event.cursor_row < 0:
            return
        if self._stage in {"broker-list", "ticker-desks"}:
            if event.cursor_row < len(self._broker_rows):
                self._broker_row_index = event.cursor_row
                self._update_broker_focus()
            return
        if self._stage not in {"accum", "preopen"}:
            return
        if event.cursor_row < len(self._rows):
            self._row_index = event.cursor_row
            self._update_focus_from_row()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter on a table selects a row.

        Board: present-only engine inspect.
        Broker list / ticker desks: desk show (home).
        """
        if self._modal_blocks_board_keys():
            return
        if event.cursor_row is None or event.cursor_row < 0:
            return
        if self._stage == "broker-list":
            if event.cursor_row < len(self._broker_rows):
                self._broker_row_index = event.cursor_row
                self._update_broker_focus()
            self._open_broker_desk_show(entry="broker-list")
            return
        if self._stage == "ticker-desks":
            if event.cursor_row < len(self._broker_rows):
                self._broker_row_index = event.cursor_row
                self._update_broker_focus()
            self._open_broker_desk_show(entry="ticker-desks")
            return
        if self._stage not in {"accum", "preopen"}:
            return
        if event.cursor_row < len(self._rows):
            self._row_index = event.cursor_row
            self._update_focus_from_row()
        self._open_detail()

    def _sync_table_cursor(self) -> None:
        table = self.query_one("#board-table", DataTable)
        if not table.row_count:
            return
        idx = (
            self._broker_row_index
            if self._stage in {"broker-list", "ticker-desks"}
            else self._row_index
        )
        table.move_cursor(row=idx, animate=False)

    def _update_broker_focus(self) -> None:
        if not self._broker_rows:
            self._focus_ticker = "—"
        else:
            row = self._broker_rows[self._broker_row_index]
            self._focus_ticker = str(getattr(row, "code", "—"))
        self._refresh_focus_only()

    def _update_focus_from_row(self) -> None:
        if not self._rows:
            self._focus_ticker = "—"
        else:
            row = self._rows[self._row_index]
            self._focus_ticker = getattr(row, "ticker", None) or row.get("ticker", "—")  # type: ignore[union-attr]
        self._refresh_focus_only()
        if self._stage == "preopen":
            self._update_preopen_evidence()
        elif self._stage == "accum":
            self._update_accum_evidence()

    def _refresh_focus_only(self) -> None:
        self.query_one("#status", Static).update(self._status_text())
        self.query_one("#side-focus", Static).update(
            "none selected"
            if self._focus_ticker == "—"
            else f"{self._focus_ticker} · Enter view · p plan"
        )

    # ── commands ───────────────────────────────────────────

    def _run_command(self, command_id: str) -> None:
        self._invalidate_agent_turn()
        if command_id == "toggle-sidebar":
            self.action_toggle_sidebar()
            return
        if command_id == "help":
            self.action_show_help()
            return
        if command_id == "empty-demo":
            self._show_empty()
            return
        if command_id == "refresh-local":
            self.action_refresh_local()
            return
        if command_id == "screen-accum":
            self._load_accum()
            return
        if command_id == "screen-preopen":
            self._load_preopen()
            return
        if command_id == "view-ticker":
            self._open_view_ticker_dashboard()
            return
        if command_id == "view-broker":
            self._open_view_broker_list()
            return
        if command_id == "plan-swing":
            self._open_plan_stage()
            return
        if command_id == "paper-log":
            self.action_paper_log()
            return
        if command_id in {"paper", "paper-notebook", "view-paper"}:
            self._open_paper_stage(ticker=self._focus_ticker)
            return
        if command_id == "fetch":
            self._open_fetch_confirm()
            return
        if command_id in {"bt-accum", "bt-swing", "assess-preopen"}:
            hints = {
                "bt-accum": "CLI: saham backtest screen accum",
                "bt-swing": "CLI: saham backtest portfolio swing",
                "assess-preopen": "CLI: saham assess pre-open <ticker>",
            }
            self.notify(hints[command_id], timeout=2.5)
            return
        self.notify(f"{command_id} · not wired", timeout=1.5)

    def _show_empty(self) -> None:
        self._recomputing = False
        self._stage = "empty"
        self._board_title = "Screen · —"
        self._meta = "waiting on local data"
        self._focus_ticker = "—"
        self._rows = []
        self._status_note = "empty · fetch explicit"
        # Re-read health so empty DB paints empty (not a stale ready line).
        self._refresh_local_cache_health()
        # Mode follows session cache health — not "board has 0 rows".
        # Ready/lag local dates ⇒ local-first; only true empty cache ⇒ no cache.
        status = getattr(self._cache_health, "status", None)
        if status in {"ready", "lag"}:
            self._mode = "local-first"
            self._meta = "local cache · no board rows"
            self._status_note = "empty board · cache present"
            notify = "Empty board · local cache present"
        elif status == "empty":
            self._mode = "no cache"
            self._meta = "waiting on local data"
            self._status_note = "empty · fetch explicit"
            notify = "Empty cache · fetch explicit"
        else:
            # unknown / loader missing: do not claim "no cache" over real disk state
            self._mode = "local-first"
            self._meta = "empty board · cache health unclear"
            self._status_note = "empty · check cache"
            notify = "Empty board · cache health unclear"
        self._refresh_chrome()
        self.notify(notify, timeout=1.2)

    # ── accum / preopen load ───────────────────────────────

    def _load_accum(self, *, keep_prior: bool | None = None) -> None:
        if self._accum_controller is None and self._accum_loader is None:
            self.notify("Screen accumulation — not wired (composition)", timeout=2.0)
            self._stage = "accum"
            self._board_title = "Screen · accumulation"
            self._meta = "loader not injected"
            self._rows = []
            self._refresh_chrome()
            return
        blank = (
            should_blank_board_for_load(
                has_visible_rows=bool(self._rows),
                current_stage=self._stage,
                current_board_kind=self._board_kind,
                target_board_kind="accum",
            )
            if keep_prior is None
            else not keep_prior
        )
        self._board_title = "Screen · accumulation"
        self._recomputing = True
        if blank:
            self._stage = "loading"
            self._meta = "local cache · recomputing"
            self._status_note = "recomputing…"
            # Do not clear rows if keep_prior was forced with empty stage edge;
            # blank path means no prior same-kind board.
            if self._board_kind != "accum":
                self._rows = []
                self._evidence_text = ""
        else:
            # Keep READY board visible (criterion 1).
            self._stage = "accum"
            self._board_kind = "accum"
            self._status_note = recomputing_status_note(
                row_count=len(self._rows),
                summary=self._board_summary,
            )
            if "recomputing" not in self._meta:
                self._meta = f"{self._meta} · recomputing" if self._meta else "recomputing"
        self._refresh_chrome()
        generation = 0
        if self._accum_controller is not None:
            # begin() invalidates prior generation (criterion 2).
            generation = self._accum_controller.begin()
        self._execute_accum(generation)

    def _load_preopen(self) -> None:
        if self._preopen_controller is None and self._preopen_loader is None:
            self.notify("Screen pre-open — not wired (composition)", timeout=2.0)
            self._stage = "preopen"
            self._board_title = "Screen · pre-open"
            self._meta = "loader not injected"
            self._rows = []
            self._refresh_chrome()
            return
        blank = should_blank_board_for_load(
            has_visible_rows=bool(self._rows),
            current_stage=self._stage,
            current_board_kind=self._board_kind,
            target_board_kind="preopen",
        )
        self._board_title = "Screen · pre-open"
        self._recomputing = True
        if blank:
            self._stage = "loading"
            self._meta = "IEP / local · recomputing"
            self._status_note = "recomputing…"
            if self._board_kind != "preopen":
                self._rows = []
                self._evidence_text = ""
        else:
            self._stage = "preopen"
            self._board_kind = "preopen"
            self._status_note = recomputing_status_note(row_count=len(self._rows))
            if "recomputing" not in self._meta:
                self._meta = f"{self._meta} · recomputing" if self._meta else "recomputing"
        self._refresh_chrome()
        generation = 0
        if self._preopen_controller is not None:
            generation = self._preopen_controller.begin()
        self._execute_preopen(generation)

    @work(thread=True, exclusive=True, group="board")
    def _execute_accum(self, generation: int) -> None:
        if self._accum_controller is not None:
            self._accum_controller.execute_generation(
                generation,
                dispatch=lambda cb, *a: dispatch_if_active(self, cb, *a),
                listener=self._on_accum_state,
            )
            return
        assert self._accum_loader is not None
        try:
            payload = self._accum_loader()
            dispatch_if_active(self, self._on_accum_payload, payload)
        except Exception as exc:
            dispatch_if_active(self, self._on_board_error, str(exc))

    @work(thread=True, exclusive=True, group="board")
    def _execute_preopen(self, generation: int) -> None:
        if self._preopen_controller is not None:
            self._preopen_controller.execute_generation(
                generation,
                dispatch=lambda cb, *a: dispatch_if_active(self, cb, *a),
                listener=self._on_preopen_state,
            )
            return
        assert self._preopen_loader is not None
        try:
            payload = self._preopen_loader()
            dispatch_if_active(self, self._on_preopen_payload, payload)
        except Exception as exc:
            dispatch_if_active(self, self._on_board_error, str(exc))

    def _on_board_error(self, message: str) -> None:
        self._recomputing = False
        self._stage = "error"
        self._error_text = message
        self._status_note = "error"
        self._refresh_chrome()

    def _on_accum_state(self, state: ScreenState) -> None:
        if state.status is ScreenStatus.LOADING:
            return
        if state.status is ScreenStatus.ERROR:
            self._on_board_error(f"{state.error_type}: {state.error_message}")
            return
        if state.status is ScreenStatus.EMPTY:
            self._recomputing = False
            self._board_source = "live"
            self._snapshot_freshness = ""
            self._board_kind = "accum"
            # Live empty success must clear last-run snapshot (criterion 4).
            invalidate_accum_board_snapshot(self._board_snapshot_path)
            self._show_empty()
            self._board_title = "Screen · accumulation"
            self._meta = "local · 0 candidates"
            self._status_note = "0 candidates · local"
            self.query_one("#side-accum", Static).update("Accum    0")
            self._refresh_chrome()
            return
        self._on_accum_payload(state.payload)

    def _on_preopen_state(self, state: ScreenState) -> None:
        if state.status is ScreenStatus.LOADING:
            return
        if state.status is ScreenStatus.ERROR:
            self._on_board_error(f"{state.error_type}: {state.error_message}")
            return
        if state.status is ScreenStatus.EMPTY:
            self._recomputing = False
            self._board_kind = "preopen"
            self._stage = "empty"
            self._board_title = "Screen · pre-open"
            self._meta = "no IEP / empty local"
            self._mode = "local-first"
            self._rows = []
            self._status_note = "pre-open empty"
            self._refresh_local_cache_health()
            status = getattr(self._cache_health, "status", None)
            if status == "empty":
                self._mode = "no cache"
            self.query_one("#side-preopen", Static).update("Pre-open 0")
            self._refresh_chrome()
            return
        self._on_preopen_payload(state.payload)

    def _on_accum_payload(self, payload: Any) -> None:
        summary = ""
        self._recomputing = False
        self._board_kind = "accum"
        self._board_source = "live"
        self._snapshot_freshness = ""
        # Workflow result carries session + display-only MCE; projection fakes may not.
        self._effective_session = getattr(payload, "effective_session", None)
        self._market_context = getattr(payload, "market_context", None)
        view = None
        if self._accum_presenter is not None:
            view = self._accum_presenter.present(payload)
            self._rows = list(view.rows)
            self._meta = view.meta
            summary = getattr(view, "summary", "") or ""
            self._board_summary = summary
            self.query_one("#side-accum", Static).update(f"Accum    {len(self._rows)}")
            # Session Cache rail is local health only (not board lag).
        else:
            self._rows = list(payload) if payload else []
            self._meta = f"local · {len(self._rows)} names"
            self._board_summary = ""
        self._board_title = "Screen · accumulation"
        self._mode = "local-first"
        self._row_index = 0
        self._status_note = summary if summary else f"{len(self._rows)} rows"
        if not self._rows:
            # Successful 0-candidate live result: invalidate prior non-empty snapshot.
            invalidate_accum_board_snapshot(self._board_snapshot_path)
            self._board_kind = "accum"
            self._show_empty()
            self._board_title = "Screen · accumulation"
            self._meta = self._meta or "local · 0 candidates"
            self._status_note = "0 candidates · local"
            self._board_summary = ""
            self._refresh_chrome()
            self.notify("Accumulation · 0 candidates (local)", timeout=2.0)
            return
        self._stage = "accum"
        self._focus_ticker = self._rows[0].ticker
        self._render_board_table()
        self._update_accum_evidence()
        self._refresh_chrome()
        table = self.query_one("#board-table", DataTable)
        table.focus()
        # No toast on open/recompute ready — chrome (meta/footer/badge) carries state
        if view is not None:
            self._persist_accum_snapshot(payload, view)

    def _on_preopen_payload(self, payload: Any) -> None:
        self._recomputing = False
        self._board_kind = "preopen"
        self._board_source = "snapshot"
        self._snapshot_freshness = ""
        snap = getattr(payload, "snapshot_date", "") or ""
        self._preopen_snapshot_date = snap.isoformat() if hasattr(snap, "isoformat") else str(snap)
        raw_warn = getattr(payload, "warnings", ()) or ()
        self._preopen_warnings = tuple(str(w) for w in raw_warn)
        self._preopen_session_strip = None
        if self._preopen_presenter is not None:
            view = self._preopen_presenter.present(payload)
            self._rows = list(view.rows)
            self._meta = view.meta
            self._preopen_session_strip = getattr(view, "session_strip", None)
            self.query_one("#side-preopen", Static).update(f"Pre-open {len(self._rows)}")
        else:
            self._rows = list(payload) if payload else []
            self._meta = f"pre-open · {len(self._rows)}"
        strip = getattr(self, "_preopen_session_strip", None)
        if strip is not None:
            self._board_title = f"Screen · pre-open · {strip.as_title_suffix()}"
            self._status_note = strip.as_meta_line()
        else:
            self._board_title = "Screen · pre-open"
            self._status_note = f"{len(self._rows)} candidates"
        self._mode = "local-first"
        self._row_index = 0
        if not self._rows:
            self._board_kind = "preopen"
            self._stage = "empty"
            self._meta = self._meta or "no IEP candidates"
            self._status_note = "pre-open empty"
            self._refresh_chrome()
            self.notify("Pre-open · no local IEP candidates", timeout=2.0)
            return
        self._stage = "preopen"
        self._focus_ticker = self._rows[0].ticker
        self._render_board_table()
        self._update_preopen_evidence()
        self._refresh_chrome()
        self.query_one("#board-table", DataTable).focus()
        n = len(self._rows)
        self.notify(f"Pre-open · {n} candidates (local snapshot)", timeout=2.0)

    def _try_restore_accum_snapshot(self) -> bool:
        """Paint last-run accum board if present (no network). Returns True if painted."""
        if self._board_snapshot_path is None:
            return False
        snap = read_accum_board_snapshot(self._board_snapshot_path)
        if snap is None:
            return False
        view = board_view_from_snapshot(snap)
        if not view.rows:
            return False
        from src.adapters.tui.chrome_cues import snapshot_accum_meta

        self._board_kind = "accum"
        self._board_source = "snapshot"
        self._recomputing = False
        self._rows = list(view.rows)
        self._board_summary = view.summary
        self._board_title = "Screen · accumulation"
        self._mode = "local-first"
        self._row_index = 0
        self._stage = "accum"
        self._focus_ticker = self._rows[0].ticker
        ident = snap.identity
        self._snapshot_freshness = snapshot_freshness_note(
            as_of=ident.as_of,
            captured_at=ident.captured_at,
            universe=ident.universe,
        )
        self._meta = snapshot_accum_meta(
            base_meta=view.meta,
            freshness=self._snapshot_freshness,
        )
        self._status_note = self._snapshot_freshness
        try:
            self.query_one("#side-accum", Static).update(f"Accum    {len(self._rows)}")
        except Exception:
            pass
        # Snapshot freshness is in status/meta; Session Cache rail stays local health.
        self._render_board_table()
        self._update_accum_evidence()
        self._refresh_chrome()
        try:
            self.query_one("#board-table", DataTable).focus()
        except Exception:
            pass
        # Silent restore — badge/meta already show snapshot · recomputing
        return True

    def _persist_accum_snapshot(self, payload: Any, view: Any) -> None:
        if self._board_snapshot_path is None:
            return
        try:
            identity = identity_from_live_payload(
                payload,
                view,
                universe=self._snapshot_universe,
            )
            snap = snapshot_from_board_view(view, identity)
            write_accum_board_snapshot(self._board_snapshot_path, snap)
        except Exception:
            # Presentation cache must never break the live board.
            return

    def _render_board_table(self) -> None:
        table = self.query_one("#board-table", DataTable)
        table.clear(columns=True)
        if self._stage == "broker-list":
            # Desk radar: DayNet + Net3/5/7/10/20 + streak (+ Δ1) — same ladder as stock desks
            from src.adapters.tui.board_cell_markup import format_broker_list_cells

            table.add_columns(
                "Code",
                "Type",
                "AsOf",
                "DayNet",
                "Net3",
                "Net5",
                "Net7",
                "Net10",
                "Net20",
                "Stk",
                "Δ1",
                "#",
                "Top",
            )
            for row in self._broker_rows:
                table.add_row(*format_broker_list_cells(row))
            if self._broker_rows:
                table.move_cursor(row=self._broker_row_index, animate=False)
            return
        if self._stage == "ticker-desks":
            # Ranked by latest tops; NetX = stock×desk last X sessions (no name col)
            from src.adapters.tui.board_cell_markup import (
                format_plain_num,
                format_signed_flow_cell,
                format_ticker_cell,
            )

            table.add_columns(
                "Code",
                "Type",
                "Role",
                "AsOf",
                "DayNet",
                "Net3",
                "Net5",
                "Net7",
                "Net10",
                "Net20",
                "Stk",
                "Δ1",
            )
            for row in self._broker_rows:
                table.add_row(
                    format_ticker_cell(str(getattr(row, "code", "?") or "?")),
                    str(getattr(row, "type_label", "—")),
                    str(getattr(row, "role", "—")),
                    format_plain_num(str(getattr(row, "as_of", "—") or "—")),
                    format_signed_flow_cell(str(getattr(row, "day_net", "—") or "—")),
                    format_signed_flow_cell(str(getattr(row, "net3", "—") or "—")),
                    format_signed_flow_cell(str(getattr(row, "net5", "—") or "—")),
                    format_signed_flow_cell(str(getattr(row, "net7", "—") or "—")),
                    format_signed_flow_cell(str(getattr(row, "net10", "—") or "—")),
                    format_signed_flow_cell(str(getattr(row, "net20", "—") or "—")),
                    format_plain_num(str(getattr(row, "streak", "—") or "—")),
                    format_signed_flow_cell(str(getattr(row, "delta1", "—") or "—")),
                )
            if self._broker_rows:
                table.move_cursor(row=self._broker_row_index, animate=False)
            return
        is_preopen = self._stage == "preopen" or self._board_kind == "preopen"
        if is_preopen:
            from src.adapters.tui.board_cell_markup import format_preopen_board_cells
            from src.adapters.tui.presenters.preopen_presenter import (
                PREOPEN_BOARD_COLUMN_LABELS,
            )

            table.add_columns(*PREOPEN_BOARD_COLUMN_LABELS)
            for row in self._rows:
                table.add_row(*format_preopen_board_cells(row))
        else:
            # Option B desk board — ADR-043 Signal/Accum + chip elevation
            from src.adapters.tui.board_cell_markup import format_accum_board_cells

            table.add_columns(
                "Ticker",
                "Signal",
                "Accum",
                "Action",
                "Phase",
                "Streak",
                "RSI",
                "Net%",
                "Disc%",
                "Price",
                "Gate",
            )
            for row in self._rows:
                table.add_row(*format_accum_board_cells(row))
        if self._rows:
            table.move_cursor(row=self._row_index, animate=False)

    def _update_preopen_evidence(self) -> None:
        if not self._rows or self._stage != "preopen":
            self._evidence_text = ""
            return
        from src.adapters.tui.presenters.preopen_presenter import build_preopen_focus

        row = self._rows[self._row_index]
        focus = build_preopen_focus(
            row,
            rank=self._row_index + 1,
            total=len(self._rows),
            session_strip=getattr(self, "_preopen_session_strip", None),
        )
        self._evidence_text = focus.strip
        ev = self.query_one("#evidence-strip", Static)
        ev.display = True
        ev.update(self._evidence_text)
        self.query_one("#side-focus", Static).update(focus.focus_sidebar)

    def _update_accum_evidence(self) -> None:
        """Focus strip: Why Action, Accum breakdown, lag + board summary."""
        if not self._rows or self._stage != "accum":
            return
        from src.adapters.tui.presenters.accum_presenter import build_accum_focus

        row = self._rows[self._row_index]
        focus = build_accum_focus(
            row,
            rank=self._row_index + 1,
            total=len(self._rows),
        )
        parts: list[str] = []
        if self._board_summary:
            parts.append(f"[#9b8fb8]Board[/]  {self._board_summary}")
        parts.append(focus.strip)
        self._evidence_text = "\n".join(parts)
        ev = self.query_one("#evidence-strip", Static)
        ev.display = True
        ev.update(self._evidence_text)
        # Do not write #side-cache here — Session Cache is local health only.
        self.query_one("#side-focus", Static).update(focus.focus_sidebar)
        if focus.lag_label and focus.lag_label != "—":
            # Keep summary in status; append lag posture when present
            base = self._board_summary or self._status_note
            if "LAG" in focus.lag_label or "ALIGNED" in focus.lag_label:
                self._status_note = f"{base} · {focus.lag_label}" if base else focus.lag_label
            self.query_one("#status", Static).update(self._status_text())
        self._paint_cache_health_sidebar()

    def _remember_return_stage(self) -> None:
        if self._stage in {"accum", "preopen"}:
            self._detail_return_stage = self._stage  # type: ignore[assignment]
        elif self._board_kind in {"accum", "preopen"}:
            self._detail_return_stage = self._board_kind  # type: ignore[assignment]
        elif self._stage not in {"detail", "plan"}:
            self._detail_return_stage = "shell"

    def _open_detail(self) -> None:
        """Board Enter: ADR-054 present-only Judge (accum) or pre-open inspect."""
        if self._stage == "empty" or self._focus_ticker in {"—", ""}:
            self.notify("Nothing to judge — run a screen first", timeout=1.5)
            return
        if not self._rows and self._stage != "detail":
            self.notify("No row focused", timeout=1.5)
            return
        ticker = self._focus_ticker
        self._invalidate_agent_turn()
        row = self._rows[self._row_index] if self._rows else None
        self._remember_return_stage()

        base = self._format_row_detail(ticker, row)
        self._detail_text = base
        self._stage = "detail"
        self._judge_ticker = str(ticker).upper()
        if self._is_accum_row(row):
            limited = getattr(row, "source", None) is None
            self._judge_limited = limited
            self._board_title = f"Judge · {ticker}"
            if limited:
                self._meta = "limited judge · j re-judge or r live"
            else:
                self._meta = "j re-judge · local"
            self._status_note = "judge"
            self._judge_detail_open = False
        elif self._is_preopen_row(row):
            self._judge_limited = False
            self._preopen_detail_open = False
            self._board_title = f"Screen · pre-open · {ticker}"
            self._meta = "inspect · local"
            self._status_note = "inspect"
        else:
            self._judge_limited = False
            self._board_title = f"Inspect · {ticker}"
            self._meta = "inspect · board row"
            self._status_note = "inspect"
        self._refresh_chrome()

    def action_rejudge_ticker(self) -> None:
        """``j``: single-ticker local re-screen for Judge stage only."""
        if self._modal_blocks_board_keys():
            return
        self._invalidate_agent_turn()
        if self._stage != "detail" or self._status_note not in {"judge", "re-judging"}:
            return
        if self._detail_return_stage == "preopen" or self._board_kind == "preopen":
            self.notify("Re-judge is for accumulation judge only", timeout=1.5)
            return
        if self._ticker_judge_loader is None:
            self.notify("Re-judge not wired · local screen path missing", timeout=2.5)
            return
        ticker = str(self._focus_ticker or self._judge_ticker or "").upper()
        if not ticker or ticker == "—":
            self.notify("No ticker to re-judge", timeout=1.5)
            return
        self._judge_generation += 1
        gen = self._judge_generation
        self._judge_ticker = ticker
        self._status_note = "re-judging"
        self._meta = f"re-judging {ticker} · local screen · generation {gen}"
        self._refresh_chrome()
        self._execute_rejudge(gen, ticker)

    @work(thread=True, exclusive=True, group="judge")
    def _execute_rejudge(self, generation: int, ticker: str) -> None:
        assert self._ticker_judge_loader is not None
        try:
            payload = self._ticker_judge_loader(ticker)
            dispatch_if_active(self, self._on_rejudge_done, generation, ticker, payload, None)
        except Exception as exc:
            dispatch_if_active(self, self._on_rejudge_done, generation, ticker, None, str(exc))

    def _on_rejudge_done(
        self,
        generation: int,
        ticker: str,
        payload: Any,
        error: str | None,
    ) -> None:
        if generation != self._judge_generation:
            return  # stale worker
        if self._stage != "detail":
            return
        if str(self._focus_ticker).upper() != str(ticker).upper():
            return
        if error is not None:
            self._status_note = "judge"
            self._meta = f"re-judge failed · {error[:80]}"
            banner = f"[#c97a72]Re-judge error[/]\n{error}\n\n"
            self._detail_text = banner + (self._detail_text or "")
            self._refresh_chrome()
            self.notify(f"Re-judge failed · {ticker}", timeout=2.5)
            return

        candidate = self._first_candidate_from_payload(payload)
        if candidate is None:
            self._status_note = "judge"
            self._meta = f"re-judge · no candidate for {ticker}"
            self._detail_text = (
                f"[#d4b06a]Re-judge[/]  no candidate for {ticker} in local cache\n\n"
                + (self._detail_text or "")
            )
            self._refresh_chrome()
            self.notify(f"Re-judge · no candidate · {ticker}", timeout=2.0)
            return

        # Update board row source so subsequent Enter is full present-only.
        self._patch_board_row_from_candidate(ticker, candidate, payload)
        row = self._rows[self._row_index] if self._rows else None
        if row is None or str(getattr(row, "ticker", "")).upper() != ticker:
            # Focused row missing: synthesize temporary row from presenter
            if self._accum_presenter is not None:
                view = self._accum_presenter.present(payload)
                row = view.rows[0] if view.rows else None
        if row is None:
            self._status_note = "judge"
            self._meta = "re-judge · present failed"
            self._refresh_chrome()
            return
        self._judge_limited = getattr(row, "source", None) is None
        self._detail_text = self._format_row_detail(ticker, row)
        self._board_title = f"Judge · {ticker}"
        self._meta = "re-judged · local screen · present-only now"
        self._status_note = "judge"
        self._refresh_chrome()
        self.notify(f"Re-judged · {ticker}", timeout=2.0)

    @staticmethod
    def _first_candidate_from_payload(payload: Any) -> Any | None:
        if payload is None:
            return None
        proj = getattr(payload, "single_projection", None) or payload
        cands = list(getattr(proj, "candidates", ()) or ())
        return cands[0] if cands else None

    def _patch_board_row_from_candidate(self, ticker: str, candidate: Any, payload: Any) -> None:
        """Replace matching board row with a fresh AccumRowView (source attached)."""
        if self._accum_presenter is None:
            return
        view = self._accum_presenter.present(payload)
        if not view.rows:
            return
        new_row = view.rows[0]
        for i, row in enumerate(self._rows):
            if str(getattr(row, "ticker", "")).upper() == ticker.upper():
                self._rows[i] = new_row
                self._row_index = i
                self._focus_ticker = new_row.ticker
                # Keep session/MCE from single-ticker result when present
                self._effective_session = getattr(
                    payload, "effective_session", self._effective_session
                )
                self._market_context = getattr(payload, "market_context", self._market_context)
                return
        # Not on board — do not invent board membership
        return

    def _open_view_ticker_dashboard(
        self,
        *,
        from_desk: bool = False,
        preserve_return: bool = False,
    ) -> None:
        """Ctrl+P View ticker: CLI-equivalent cache dashboard (GetTickerDashboard)."""
        if self._focus_ticker in {"—", ""}:
            self.notify("Nothing to view — focus a ticker first", timeout=1.5)
            return
        ticker = str(self._focus_ticker).upper()
        if from_desk:
            self._view_from_desk = True
            # Keep desk code; do not rewrite board return via remember.
        else:
            self._view_from_desk = False
            if not preserve_return:
                self._remember_return_stage()
            self._broker_page = None
        self._stage = "loading"
        self._board_title = f"View · ticker · {ticker}"
        self._meta = "local cache"
        self._status_note = "view ticker"
        self._ticker_detail_open = False  # brief default (same dual as Judge)
        self._ticker_job = None
        self._ticker_job_text = None
        try:
            desk = self.query_one("#ticker-desk")
            if hasattr(desk, "set_job_view"):
                desk.set_job_view(None)  # type: ignore[attr-defined]
            elif hasattr(desk, "set_active_job"):
                desk.set_active_job(None)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._refresh_chrome()
        self._execute_view_ticker(ticker)

    def _open_view_broker_list(self) -> None:
        """Ctrl+P View broker: tracked desk list → Enter opens desk show."""
        from src.adapters.tui.chrome_cues import broker_list_loading_meta

        if self._stage in {"accum", "preopen"}:
            self._broker_list_return = self._stage  # type: ignore[assignment]
        elif self._board_kind in {"accum", "preopen"}:
            self._broker_list_return = self._board_kind  # type: ignore[assignment]
        else:
            self._broker_list_return = "shell"
        self._ticker_desks_stock = None
        self._desk_entry = None
        self._stage = "loading"
        self._board_title = "View · broker list"
        self._meta = broker_list_loading_meta()
        self._status_note = "loading broker list"
        self._mode = "local-first"
        self._refresh_chrome()
        self._execute_broker_list()

    def _open_ticker_desks(self, stock: str) -> None:
        """From view ticker: stock → top desks (ticker-desks stage)."""
        stock = str(stock or "").upper()
        if not stock or stock == "—":
            self.notify("No ticker focused", timeout=1.5)
            return
        self._ticker_desks_stock = stock
        self._view_from_desk = False
        self._broker_desk_code = None
        self._broker_page = None
        self._desk_entry = None
        from src.adapters.tui.chrome_cues import ticker_desks_title

        self._stage = "loading"
        self._board_title = ticker_desks_title(stock)
        self._meta = f"loading desks · {stock} · local cache"
        self._status_note = "view ticker desks"
        self._refresh_chrome()
        self._execute_ticker_desks(stock)

    def _restore_ticker_desks_table(self) -> None:
        """Return from desk show to the stock→desks table without re-fetch."""
        from src.adapters.tui.chrome_cues import broker_radar_meta, ticker_desks_title

        stock = self._ticker_desks_stock or "—"
        self._broker_page = None
        self._broker_desk_code = None
        self._view_from_desk = False
        self._desk_entry = "ticker-desks"
        self._stage = "ticker-desks"
        self._plan_running = False
        self._board_title = ticker_desks_title(stock)
        partial = any(
            bool(getattr(r, "has_partial_netx", False) or getattr(r, "partial_net", False))
            for r in (self._broker_rows or [])
        )
        self._meta = broker_radar_meta(
            desk_count=len(self._broker_rows or []),
            from_stock=str(stock),
            has_partial_netx=partial,
            note="esc ticker",
        )
        self._status_note = "view ticker desks"
        if self._broker_rows and 0 <= self._broker_row_index < len(self._broker_rows):
            self._focus_ticker = str(
                getattr(self._broker_rows[self._broker_row_index], "code", "—")
            )
        self._render_board_table()
        self._refresh_chrome()
        self.query_one("#board-table", DataTable).focus()

    @work(thread=True, exclusive=True, group="detail")
    def _execute_broker_list(self) -> None:
        try:
            if self._broker_list_loader is not None:
                rows = self._broker_list_loader()
            else:
                rows = []
            dispatch_if_active(self, self._on_broker_list_ready, rows)
        except Exception as exc:
            dispatch_if_active(self, self._on_board_error, f"view broker list: {exc}")

    @work(thread=True, exclusive=True, group="detail")
    def _execute_ticker_desks(self, stock: str) -> None:
        try:
            if self._ticker_desks_loader is not None:
                payload = self._ticker_desks_loader(stock)
            else:
                payload = None
            dispatch_if_active(self, self._on_ticker_desks_ready, stock, payload)
        except Exception as exc:
            dispatch_if_active(self, self._on_board_error, f"view ticker desks: {exc}")

    def _on_broker_list_ready(self, rows: Any) -> None:
        self._broker_rows = list(rows or [])
        self._broker_row_index = 0
        self._broker_page = "list"
        self._broker_desk_code = None
        self._broker_jump_ticker = None
        self._view_from_desk = False
        self._desk_entry = "broker-list"
        if not self._broker_rows:
            self._stage = "empty"
            self._board_kind = "none"
            self._board_title = "View · broker list"
            self._meta = "no tracked desks in config"
            self._status_note = "broker list empty"
            self._refresh_chrome()
            self.notify("View broker · no tracked desks", timeout=2.0)
            return
        from src.adapters.tui.chrome_cues import broker_list_title, broker_radar_meta

        self._stage = "broker-list"
        self._focus_ticker = str(getattr(self._broker_rows[0], "code", "—"))
        self._board_title = broker_list_title()
        with_data = sum(1 for r in self._broker_rows if getattr(r, "has_data", True))
        partial = any(
            bool(getattr(r, "has_partial_netx", False) or getattr(r, "partial_net", False))
            for r in self._broker_rows
        )
        self._meta = broker_radar_meta(
            desk_count=len(self._broker_rows),
            with_flow=with_data,
            has_partial_netx=partial,
            note="sorted |Net5|",
        )
        self._status_note = "view broker list"
        self._render_board_table()
        self._refresh_chrome()
        self.query_one("#board-table", DataTable).focus()
        self.notify(f"View broker · {len(self._broker_rows)} desks", timeout=2.0)

    def _on_ticker_desks_ready(self, stock: str, payload: Any) -> None:
        if self._ticker_desks_stock != stock:
            return  # stale worker
        rows = list(getattr(payload, "rows", ()) or ()) if payload is not None else []
        as_of = getattr(payload, "as_of", None) if payload is not None else None
        note = getattr(payload, "note", None) if payload is not None else None
        self._broker_rows = rows
        self._broker_row_index = 0
        self._broker_page = None
        self._broker_desk_code = None
        self._broker_jump_ticker = None
        self._view_from_desk = False
        self._desk_entry = "ticker-desks"
        from src.adapters.tui.chrome_cues import broker_radar_meta, ticker_desks_title

        self._stage = "ticker-desks"
        self._board_title = ticker_desks_title(stock)
        as_of_s = str(as_of) if as_of else "—"
        note_s = str(note) if note else ""
        partial = any(
            bool(getattr(r, "has_partial_netx", False) or getattr(r, "partial_net", False))
            for r in self._broker_rows
        )
        if not self._broker_rows:
            self._meta = broker_radar_meta(
                desk_count=0,
                from_stock=stock,
                as_of=as_of_s,
                note=note_s or None,
                has_partial_netx=False,
            )
            self._status_note = "view ticker desks"
            self._focus_ticker = stock
            self._render_board_table()
            self._refresh_chrome()
            self.query_one("#board-table", DataTable).focus()
            self.notify(f"Desks · {stock} · empty", timeout=2.0)
            return
        self._focus_ticker = str(getattr(self._broker_rows[0], "code", "—"))
        self._meta = broker_radar_meta(
            desk_count=len(self._broker_rows),
            from_stock=stock,
            as_of=as_of_s,
            note=note_s or None,
            has_partial_netx=partial,
        )
        self._status_note = "view ticker desks"
        self._render_board_table()
        self._refresh_chrome()
        self.query_one("#board-table", DataTable).focus()
        self.notify(
            f"Ticker desks · {stock} · {len(self._broker_rows)} · {note_s}",
            timeout=2.0,
        )

    def _open_broker_desk_show(
        self,
        code: str | None = None,
        *,
        entry: str | None = None,
    ) -> None:
        if code is None:
            if not self._broker_rows:
                self.notify("No desk focused", timeout=1.5)
                return
            row = self._broker_rows[self._broker_row_index]
            code = str(getattr(row, "code", "") or "").upper()
        code = str(code or "").upper()
        if not code:
            return
        if entry is not None:
            self._desk_entry = entry
        elif self._stage == "ticker-desks":
            self._desk_entry = "ticker-desks"
        elif self._stage == "broker-list":
            self._desk_entry = "broker-list"
        # else keep existing _desk_entry (deep → show trail)
        self._broker_desk_code = code
        self._broker_page = "show"
        self._view_from_desk = False
        if self._desk_entry == "broker-list":
            self._detail_return_stage = "broker-list"
        # ticker-desks entry keeps board return in _detail_return_stage for later
        esc_hint = "esc desks" if self._desk_entry == "ticker-desks" else "esc list"
        # From list/desks: named loading body (never keep_board unmask of accum).
        # From deep→home trail already on detail: stay on detail instrument.
        if self._stage in {"broker-list", "ticker-desks"}:
            self._stage = "loading"
        else:
            self._stage = "detail"
        self._board_title = f"View · broker show · {code}"
        self._meta = f"desk home · t/f/h/m deep · v stock · {esc_hint}"
        self._status_note = "view broker show"
        self._refresh_chrome()
        self._execute_broker_show(code)

    def _open_broker_deep(self, page: str) -> None:
        code = self._broker_desk_code
        if not code:
            return
        self._broker_page = page
        self._view_from_desk = False
        titles = {
            "top": f"View · broker top-stocks · {code}",
            "flow": f"View · broker flow · {code}",
            "history": f"View · broker history · {code}",
            "matrix": f"View · broker top-matrix · {code}",
            "cal": f"View · broker calendar · {code}",
        }
        # Chip/key deep pages: stay on detail instrument (no board unmask under click)
        self._stage = "detail"
        self._board_title = titles.get(page, f"View · broker · {code}")
        deep_lab = {
            "top": "buy/sell",
            "flow": "flow",
            "history": "history",
            "matrix": "top 5",
            "cal": "calendar",
        }.get(page, page)
        self._meta = f"desk deep · {deep_lab} · loading · esc home · local cache"
        self._status_note = f"view broker {page}"
        # Clear prior page model so paint shows honest empty/loading model
        if page == "top":
            self._broker_desk_top_model = None
        elif page == "flow":
            self._broker_desk_flow_model = None
        elif page == "history":
            self._broker_desk_history_model = None
        elif page == "matrix":
            self._broker_desk_matrix_model = None
        elif page == "cal":
            self._broker_desk_calendar_model = None
        self._refresh_chrome()
        self._execute_broker_deep(code, page)

    @work(thread=True, exclusive=True, group="detail")
    def _execute_broker_show(self, code: str) -> None:
        try:
            payload = (
                self._broker_show_loader(code) if self._broker_show_loader is not None else None
            )
            home_model = None
            if payload is None:
                text = f"[bold]{code}[/]\n\n[dim]broker show loader not wired[/]"
                jump = None
            elif isinstance(payload, str):
                text = payload
                jump = None
            else:
                text = str(getattr(payload, "text", "") or "")
                jump = getattr(payload, "jump_ticker", None)
                jump = str(jump).upper() if jump else None
                home_model = getattr(payload, "model", None)
            if not text.strip():
                text = (
                    f"[bold]{code}[/]\n\n"
                    "[dim]no broker_daily_flow for this desk · fetch broker data[/]"
                )
            # When loader only returns text (tests), still try a minimal structured model
            # so the desk widget can paint hub + empty/day facts from scraper text path.
            if home_model is None:
                from src.adapters.tui.broker_desk_home_model import (
                    build_broker_desk_home_model,
                    format_broker_desk_home_scraper_text,
                )

                # Always paint structured desk shell (never text dump as primary).
                home_model = build_broker_desk_home_model(
                    None,
                    code=code,
                    empty_reason="no desk day-net in local cache · fetch broker data",
                )
                if not text or "no broker_daily_flow" in text.lower():
                    text = format_broker_desk_home_scraper_text(home_model)
            esc_line = "  esc desks" if self._desk_entry == "ticker-desks" else "  esc list"
            if "Actions (TUI)" not in text:
                actions = (
                    "\n\n[#9b8fb8]Actions (TUI)[/]\n"
                    "  t top-stocks · f flow · c calendar · h history · m top-matrix\n"
                    "  v view ticker (top buy stock)\n"
                    f"{esc_line}\n"
                )
                text = text.rstrip() + actions
            header = (
                f"[bold #e8e8e8]View · broker show · {code}[/]\n"
                f"[dim]local cache · tracked desk[/]\n\n"
            )
            dispatch_if_active(
                self,
                self._on_broker_page_ready,
                code,
                "show",
                header + text,
                jump,
                home_model,
            )
        except Exception as exc:
            dispatch_if_active(
                self,
                self._on_broker_page_ready,
                code,
                "show",
                f"[bold]View · broker show · {code}[/]\n\n[dim]error: {exc}[/]",
                None,
                None,
            )

    @work(thread=True, exclusive=True, group="detail")
    def _execute_broker_deep(self, code: str, page: str) -> None:
        try:
            loader = {
                "top": self._broker_top_loader,
                "flow": self._broker_flow_loader,
                "history": self._broker_history_loader,
                "matrix": self._broker_matrix_loader,
                "cal": self._broker_calendar_loader,
            }.get(page)
            raw = loader(code) if loader is not None else None
            deep_model = None
            jump = self._broker_jump_ticker
            if raw is None:
                text = ""
            elif isinstance(raw, str):
                text = raw
            else:
                text = str(getattr(raw, "text", "") or "")
                deep_model = getattr(raw, "model", None)
                jt = getattr(raw, "jump_ticker", None)
                if jt:
                    jump = str(jt).upper()
            if not text.strip():
                text = f"[bold]{code}[/]\n\n[dim]no data · loader missing or empty[/]"
            # Always structured deep shell so widget path paints (never body-only dump).
            empty_reason = "no desk data in local cache · fetch broker data"
            if page == "matrix" and deep_model is None:
                from src.adapters.tui.broker_desk_matrix_model import (
                    build_broker_desk_matrix_model,
                )

                deep_model = build_broker_desk_matrix_model(
                    None, code=code, empty_reason=empty_reason
                )
            if page == "top" and deep_model is None:
                from src.adapters.tui.broker_desk_top_model import (
                    build_broker_desk_top_model,
                )

                deep_model = build_broker_desk_top_model(None, code=code, empty_reason=empty_reason)
            if page == "flow" and deep_model is None:
                from src.adapters.tui.broker_desk_flow_model import (
                    build_broker_desk_flow_model,
                )

                deep_model = build_broker_desk_flow_model(
                    None, code=code, empty_reason=empty_reason
                )
            if page == "history" and deep_model is None:
                from src.adapters.tui.broker_desk_history_model import (
                    build_broker_desk_history_model,
                )

                deep_model = build_broker_desk_history_model(
                    None, code=code, empty_reason=empty_reason
                )
            if page == "cal" and deep_model is None:
                from src.adapters.tui.broker_desk_calendar_model import (
                    build_broker_desk_calendar_model,
                )

                deep_model = build_broker_desk_calendar_model(
                    None, code=code, empty_reason=empty_reason
                )
            titles = {
                "top": "top-stocks",
                "flow": "flow",
                "history": "history",
                "matrix": "top-matrix",
            }
            label = titles.get(page, page)
            header = (
                f"[bold #e8e8e8]View · broker {label} · {code}[/]\n"
                f"[dim]local cache · tracked desk[/]\n\n"
            )
            footer = (
                "\n\n[#9b8fb8]Actions[/]\n  t/f/c/h/m switch deep · v view ticker · esc desk home\n"
            )
            dispatch_if_active(
                self,
                self._on_broker_page_ready,
                code,
                page,
                header + text + footer,
                jump,
                None,
                deep_model if page == "matrix" else None,
                deep_model if page == "top" else None,
                deep_model if page == "flow" else None,
                deep_model if page == "history" else None,
                deep_model if page == "cal" else None,
            )
        except Exception as exc:
            dispatch_if_active(
                self,
                self._on_broker_page_ready,
                code,
                page,
                f"[bold]View · broker {page} · {code}[/]\n\n[dim]error: {exc}[/]",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )

    def _on_broker_page_ready(
        self,
        code: str,
        page: str,
        text: str,
        jump_ticker: str | None,
        home_model: Any | None = None,
        matrix_model: Any | None = None,
        top_model: Any | None = None,
        flow_model: Any | None = None,
        history_model: Any | None = None,
        calendar_model: Any | None = None,
    ) -> None:
        # Drop stale worker results when user already moved on.
        if self._broker_desk_code != code or self._broker_page != page:
            return
        if jump_ticker is not None:
            self._broker_jump_ticker = jump_ticker
        self._detail_text = text
        self._broker_desk_home_model = home_model if page == "show" else None
        self._broker_desk_matrix_model = matrix_model if page == "matrix" else None
        self._broker_desk_top_model = top_model if page == "top" else None
        self._broker_desk_flow_model = flow_model if page == "flow" else None
        self._broker_desk_history_model = history_model if page == "history" else None
        self._broker_desk_calendar_model = calendar_model if page == "cal" else None
        self._stage = "detail"
        titles = {
            "show": f"View · broker show · {code}",
            "top": f"View · broker top-stocks · {code}",
            "flow": f"View · broker flow · {code}",
            "history": f"View · broker history · {code}",
            "matrix": f"View · broker top-matrix · {code}",
            "cal": f"View · broker calendar · {code}",
        }
        self._board_title = titles.get(page, f"View · broker · {code}")
        self._meta = "local cache · esc trail"
        status_page = {"matrix": "top-matrix", "cal": "calendar"}.get(page, page)
        self._status_note = f"view broker {status_page}"
        self._refresh_chrome()

    @work(thread=True, exclusive=True, group="detail")
    def _execute_view_ticker(self, ticker: str) -> None:
        from src.adapters.tui.ticker_desk_model import (
            TickerDeskModel,
            build_ticker_desk_model_from_text,
        )
        from src.adapters.tui.ticker_desk_present import model_from_loader_result

        try:
            if self._ticker_detail_loader is not None:
                raw = self._ticker_detail_loader(ticker)
            else:
                raw = build_ticker_desk_model_from_text(
                    ticker=ticker,
                    body="view ticker loader not wired (composition)",
                )
            model = model_from_loader_result(ticker, raw)
            if not isinstance(model, TickerDeskModel):
                model = build_ticker_desk_model_from_text(ticker=ticker, body=str(raw or ""))
            dispatch_if_active(self, self._on_view_ticker_ready, ticker, model)
        except Exception as exc:
            err_model = build_ticker_desk_model_from_text(
                ticker=ticker,
                body=f"error: {exc}",
            )
            dispatch_if_active(self, self._on_view_ticker_ready, ticker, err_model)

    def _on_view_ticker_ready(self, ticker: str, model_or_text: Any) -> None:
        from src.adapters.tui.ticker_desk_model import (
            TickerDeskModel,
            build_ticker_desk_model_from_text,
        )
        from src.adapters.tui.ticker_desk_present import model_from_loader_result

        if isinstance(model_or_text, TickerDeskModel):
            model = model_or_text
        else:
            model = model_from_loader_result(ticker, model_or_text)
        if not isinstance(model, TickerDeskModel):
            model = build_ticker_desk_model_from_text(ticker=ticker, body=str(model_or_text or ""))
        actions = "\n\n[#9b8fb8]Actions (TUI)[/]\n  b f o x n jobs · d detail · Tab chips\n" + (
            "  esc → desk home\n" if self._view_from_desk else "  esc trail\n"
        )
        body = model.body or ""
        if "Actions (TUI)" not in body:
            body = body + actions
        # Rebuild model with actions in depth body
        from dataclasses import replace

        model = replace(model, body=body.strip())
        self._ticker_desk_model = model
        self._ticker_detail_open = False  # brief default · d → detail is-on
        self._detail_text = model.as_text()
        self._stage = "detail"
        self._board_title = f"View · ticker · {ticker}"
        # Density state = [d] is-on only — no brief/detail meta text
        if self._view_from_desk:
            self._meta = "from desk"
            self._broker_page = None  # not a desk page; trail via _view_from_desk
        else:
            self._meta = "local cache"
        self._status_note = "view ticker"
        self._focus_ticker = ticker
        self._refresh_chrome()

    @staticmethod
    def _is_accum_row(row: Any) -> bool:
        if row is None:
            return False
        return all(hasattr(row, k) for k in ("signal", "accum", "action", "gate"))

    @staticmethod
    def _is_preopen_row(row: Any) -> bool:
        if row is None:
            return False
        # Locked pre-open row shape (Act replaces Grd theater)
        if all(hasattr(row, k) for k in ("iep", "action", "risk", "delta_pct", "ncp")):
            return True
        # Legacy test doubles that still expose grade
        return all(hasattr(row, k) for k in ("iep", "grade", "risk", "delta_pct"))

    def _format_row_detail(self, ticker: str, row: Any) -> str:
        if row is None:
            return f"[bold]{ticker}[/]\n\n[dim]No row payload[/]"

        if self._is_accum_row(row) or self._board_kind == "accum":
            if self._is_accum_row(row):
                from src.adapters.tui.presenters.accum_engine_inspect_presenter import (
                    present_accum_engine_inspect,
                )

                seq_facts, seq_unavail = self._load_phase_sequence_for_judge(ticker, row)
                view = present_accum_engine_inspect(
                    row,
                    rank=self._row_index + 1,
                    total=max(len(self._rows), 1),
                    board_summary=self._board_summary,
                    effective_session=self._effective_session,
                    market_context=self._market_context,
                    phase_sequence=seq_facts,
                    phase_sequence_unavailable=seq_unavail,
                )
                return view.text

        if self._is_preopen_row(row) or self._board_kind == "preopen":
            if self._is_preopen_row(row):
                from src.adapters.tui.presenters.preopen_engine_inspect_presenter import (
                    present_preopen_engine_inspect,
                )

                view = present_preopen_engine_inspect(
                    row,
                    rank=self._row_index + 1,
                    total=max(len(self._rows), 1),
                    snapshot_date=self._preopen_snapshot_date,
                    board_meta=self._meta,
                    warnings=self._preopen_warnings,
                )
                return view.text

        # Unknown row shape: lean field dump
        lines = [f"[bold #e8e8e8]{ticker}[/]", ""]
        for key, label in (
            ("action", "Act"),
            ("iep", "IEP"),
            ("delta_pct", "Δ%"),
            ("iev", "IEV"),
            ("ncp", "NCP"),
            ("delta_iev", "ΔIEV"),
            ("risk", "Risk"),
            ("name", "Name"),
        ):
            if hasattr(row, key):
                val = getattr(row, key)
                if val is not None and val != "":
                    lines.append(f"[dim]{label:10}[/] {val}")
        lines.append("")
        lines.append("[dim]esc back · Ctrl+P[/]")
        return "\n".join(lines)

    def _open_plan_stage(self) -> None:
        """p switches main stage to Plan and auto-runs structure desk (ADR-054).

        No confirm modal. esc returns to the board. No broker order.
        """
        if self._stage == "empty" or self._focus_ticker in {"—", ""}:
            self.notify("Nothing to plan — fetch / screen first", timeout=1.5)
            return
        if self._stage in {"accum", "preopen"}:
            self._detail_return_stage = self._stage  # type: ignore[assignment]
        elif self._stage == "detail" and self._detail_return_stage == "shell":
            if self._board_kind in {"accum", "preopen"}:
                self._detail_return_stage = self._board_kind  # type: ignore[assignment]
        elif self._stage not in {"detail", "plan"} and self._board_kind in {
            "accum",
            "preopen",
        }:
            self._detail_return_stage = self._board_kind  # type: ignore[assignment]

        ticker = self._focus_ticker
        self._plan_ticker = ticker
        self._plan_result = ""
        self._plan_structure = None
        self._plan_running = True
        self._paper_outcome = ""
        self._stage = "plan"
        self._board_title = f"Plan · {ticker} · structure"
        self._meta = "structure desk · local · no broker order"
        self._status_note = "plan running"
        self._refresh_chrome()

        if self._plan_runner is None:
            self._plan_running = False
            self._plan_result = "no plan runner wired · stub only"
            self._plan_structure = None
            self._status_note = "plan stub"
            self._refresh_chrome()
            self.notify(f"Plan · {ticker} · stub (no runner)", timeout=2.0)
            return
        self._execute_plan(ticker)

    def _plan_body_text(self) -> str:
        from src.adapters.tui.presenters.plan_stage_presenter import present_plan_stage

        row = None
        if self._rows and 0 <= self._row_index < len(self._rows):
            row = self._rows[self._row_index]
        on_preopen = self._detail_return_stage == "preopen" or self._board_kind == "preopen"
        source = "Screen · pre-open" if on_preopen else "Screen · accumulation"
        view = present_plan_stage(
            row,
            ticker=self._plan_ticker or self._focus_ticker,
            source=source,
            rank=self._row_index + 1,
            total=max(len(self._rows), 1),
            result_line=self._plan_result,
            structure=self._plan_structure,
            running=self._plan_running,
        )
        return view.text

    @work(thread=True, exclusive=True, group="plan")
    def _execute_plan(self, ticker: str) -> None:
        try:
            result = self._plan_runner(ticker) if self._plan_runner else None
            dispatch_if_active(self, self._on_plan_done, ticker, result)
        except Exception as exc:
            from src.adapters.tui.plan_structure_result import PlanStructureResult

            err = PlanStructureResult(
                summary=f"error: {exc}",
                ticker=ticker,
                incomplete_reason=str(exc)[:120],
            )
            dispatch_if_active(self, self._on_plan_done, ticker, err)

    def _on_plan_done(self, ticker: str, result: Any) -> None:
        from src.adapters.tui.plan_structure_result import plan_structure_from_runner_object

        self._plan_running = False
        struct = plan_structure_from_runner_object(result)
        if isinstance(result, str):
            # Legacy string-only delivery
            struct = plan_structure_from_runner_object(type("R", (), {"summary": result})())
        self._plan_structure = struct
        self._plan_result = struct.summary
        self._status_note = "plan done"
        # Stay on plan stage so the page is the result surface (variant A).
        if self._stage == "plan" and self._plan_ticker == ticker:
            self._meta = "structure result · inherits Action · no broker order · l paper log"
            self._refresh_chrome()
        self.notify(f"Plan · {ticker} · {struct.summary}", timeout=2.5)

    def action_paper_log(self) -> None:
        """Explicit paper notebook log from plan stage (confirm first; no broker order)."""
        if self._modal_blocks_board_keys():
            return
        if self._stage != "plan":
            self.notify("Paper log is on plan stage (p · then l)", timeout=1.8)
            return
        if self._plan_running:
            self.notify("Plan still running — wait for structure result", timeout=1.8)
            return
        ticker = str(self._plan_ticker or self._focus_ticker or "").strip().upper()
        if not ticker or ticker == "—":
            self.notify("No ticker to log", timeout=1.5)
            return
        struct = self._plan_structure
        if struct is None:
            self.notify("No structure yet — run plan (p) first", timeout=1.8)
            return
        incomplete = str(getattr(struct, "incomplete_reason", "") or "").strip()
        if incomplete and not getattr(struct, "plan_id_short", ""):
            self.notify(f"Cannot paper log · {incomplete}", timeout=2.5)
            return
        from src.adapters.tui.paper_log_display import plan_text_from_structure

        # Geometry for confirm from structure desk fields only (notebook UI).
        plan_text = plan_text_from_structure(struct, ticker=ticker)
        self._open_paper_log_confirm(ticker=ticker, plan_text=plan_text)

    def _open_paper_log_confirm(self, *, ticker: str, plan_text: str) -> None:
        from src.adapters.tui.screens.paper_log_confirm import PaperLogConfirmModal

        def _on_dismiss(confirmed: bool | None) -> None:
            if not confirmed:
                return
            if self._paper_log_runner is None:
                self.notify(
                    "Paper log not wired · plan · l unavailable",
                    timeout=2.5,
                )
                return
            self._status_note = "paper logging"
            self._refresh_chrome()
            self._execute_paper_log(ticker)

        self.push_screen(
            PaperLogConfirmModal(plan_text=plan_text, ticker=ticker),
            _on_dismiss,
        )

    @work(thread=True, exclusive=True, group="paper-log")
    def _execute_paper_log(self, ticker: str) -> None:
        try:
            assert self._paper_log_runner is not None
            result = self._paper_log_runner(ticker)
            dispatch_if_active(self, self._on_paper_log_done, ticker, result, None)
        except Exception as exc:
            dispatch_if_active(self, self._on_paper_log_done, ticker, None, str(exc))

    def _on_paper_log_done(self, ticker: str, result: Any, error: str | None) -> None:
        from src.adapters.tui.paper_log_display import format_paper_outcome_tape
        from src.adapters.tui.paper_log_result import PaperLogResult

        if error is not None:
            self._status_note = "paper"
            self._paper_outcome = (
                f"[bold #c97a72]PAPER TAPE · FAILED[/]\n"
                f"{ticker} · {error[:120]}\n"
                "[dim]no broker order[/]"
            )
            self._paper_tape.append(self._paper_outcome)
            self._open_paper_stage()
            self.notify(f"Paper log failed · {error[:100]}", timeout=2.5)
            return

        if isinstance(result, PaperLogResult):
            self._paper_outcome = format_paper_outcome_tape(result)
            self._paper_tape.append(result)
            msg = result.message
            self._open_paper_stage(ticker=ticker)
            # Open stage defaults status to "paper"; restore outcome-specific cue.
            if result.refused:
                self._status_note = "paper"
                self._refresh_chrome()
                self.notify(f"Paper log refused · {msg}", timeout=2.8)
                return
            if result.written:
                self._status_note = "paper logged"
                self._refresh_chrome()
                self.notify(msg, timeout=3.0)
                return
            # Idempotent non-write (duplicate) — structure already done.
            self._status_note = "plan done"
            self._refresh_chrome()
            self.notify(msg, timeout=2.8)
            return
        # Duck-typed result
        written = bool(getattr(result, "written", False))
        message = str(getattr(result, "message", result) or result)
        duck = type(
            "R",
            (),
            {
                "ticker": ticker,
                "written": written,
                "message": message,
                "refused": False,
            },
        )()
        self._paper_outcome = format_paper_outcome_tape(duck)
        self._paper_tape.append(duck)
        self._open_paper_stage(ticker=ticker)
        self._status_note = "paper logged" if written else "plan done"
        self._refresh_chrome()
        self.notify(message[:160], timeout=2.8)

    def _open_paper_stage(self, *, ticker: str = "") -> None:
        """Show paper notebook stage (tape hierarchy)."""
        if ticker:
            self._focus_ticker = str(ticker).upper()
        self._stage = "paper"
        self._board_title = "Paper · notebook"
        self._meta = "session tape · paper only"
        self._status_note = "paper"
        self._refresh_chrome()

    def _repaint_plan_if_open(self) -> None:
        """Refresh Geometry mast + paper tape when still on plan stage."""
        if self._stage != "plan":
            return
        try:
            body = self.query_one("#stage-body", Static)
            self._paint_plan_stage(body=body)
        except Exception:
            return

    def _load_phase_sequence_for_judge(self, ticker: str, row: Any) -> tuple[Any, str | None]:
        """Read-only ledger sequence for Judge; never network, never write."""
        if self._phase_history_loader is None:
            return (), "phase history loader not wired"
        before = self._resolve_phase_before_date(row)
        if before is None:
            return (), "cannot load sequence without as_of"
        try:
            facts = self._phase_history_loader(str(ticker).upper(), before)
        except Exception:
            return (), "phase history read failed"
        if facts is None:
            return (), None
        return facts, None

    def _resolve_phase_before_date(self, row: Any) -> Any | None:
        """Exclusive upper bound for ledger list_rows_before (local session only)."""
        from datetime import date as date_cls

        sess = self._effective_session
        if sess is not None:
            for attr in ("analysis_as_of", "latest_completed_session"):
                val = getattr(sess, attr, None)
                if isinstance(val, date_cls):
                    return val
                if val is not None:
                    try:
                        return date_cls.fromisoformat(str(val)[:10])
                    except ValueError:
                        pass
        source = getattr(row, "source", None) if row is not None else None
        if source is not None:
            for attr in ("latest_candle_date",):
                val = getattr(source, attr, None)
                if isinstance(val, date_cls):
                    # ledger uses strict < before_date; include candle day via +1 day
                    from datetime import timedelta

                    return val + timedelta(days=1)
            fr = getattr(source, "freshness", None)
            if fr is not None:
                val = getattr(fr, "candle_as_of", None)
                if isinstance(val, date_cls):
                    from datetime import timedelta

                    return val + timedelta(days=1)
        # Live screen default matches accumulation UC (date.today as before_date).
        return date_cls.today()

    def _refresh_local_cache_health(self) -> None:
        """Paint local-only cache health (no network). Safe on failure."""
        if self._cache_health_loader is None:
            self._cache_health = None
            self._cache_next_step = "Fetch is explicit."
            return
        try:
            health = self._cache_health_loader()
        except Exception:
            health = None
        self._cache_health = health
        if health is None:
            self._cache_next_step = "Fetch is explicit."
            return
        self._cache_next_step = getattr(health, "next_step", None) or "Fetch is explicit."

    def _paint_cache_health_sidebar(self) -> None:
        try:
            cache_el = self.query_one("#side-cache", Static)
            online_el = self.query_one("#side-online", Static)
        except Exception:
            return
        health = self._cache_health
        if health is None:
            cache_el.update("Cache    —")
            online_el.update(self._online_note or self._cache_next_step)
            return
        line = getattr(health, "sidebar_cache_line", None)
        if callable(line):
            cache_el.update(line())
        else:
            from src.adapters.tui.local_cache_health import format_sidebar_cache_line

            cache_el.update(format_sidebar_cache_line(health))
        if self._online_note:
            online_el.update(self._online_note)
            return
        next_line = getattr(health, "sidebar_next_line", None)
        if callable(next_line):
            online_el.update(next_line())
        else:
            online_el.update(self._cache_next_step)

    def _open_fetch_confirm(self) -> None:
        from src.adapters.tui.screens.fetch_confirm import FetchConfirmModal

        plan_text = "Fetch market data for configured universe (explicit online)."
        if self._fetch_previewer is not None:
            try:
                plan = self._fetch_previewer()
                plan_text = getattr(plan, "summary", None) or str(plan)
            except Exception as exc:
                plan_text = f"Preview failed: {exc}"

        def _on_dismiss(confirmed: bool | None) -> None:
            if not confirmed:
                return
            if self._fetch_runner is None:
                self.notify("Fetch not wired · use explicit data fetch later", timeout=2.5)
                return
            self._mode = "online · explicit"
            self._stage = "loading"
            self._refresh_chrome()
            self._execute_fetch()

        self.push_screen(FetchConfirmModal(plan_text=plan_text), _on_dismiss)

    @work(thread=True, exclusive=True, group="fetch")
    def _execute_fetch(self) -> None:
        try:
            assert self._fetch_runner is not None
            self._fetch_runner()
            dispatch_if_active(self, self._on_fetch_done)
        except Exception as exc:
            dispatch_if_active(self, self._on_board_error, f"fetch: {exc}")

    def _on_fetch_done(self) -> None:
        self._mode = "local-first"
        self._online_note = "Last fetch ok · now local"
        self._refresh_local_cache_health()
        self._paint_cache_health_sidebar()
        self.notify("Fetch complete · reloading accumulation", timeout=2.0)
        self._load_accum()


def run_tui() -> None:
    """Construct and run the optional cockpit from its composition root."""
    from src.adapters.tui.composition import create_tui_app

    create_tui_app().run()
