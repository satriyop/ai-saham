"""OpenCode-style daily cockpit Textual app (optional TUI adapter).

Phases: shell/palette (0–1), boards (2–3), plan/fetch (4), harden (5).
Design: docs/design/tui-cockpit-opencode.md · ADR-051

Layer: Adapter
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Static

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
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        # Desk hub keys (no-op outside broker show/deep pages)
        Binding("t", "broker_top", "Desk top", show=False),
        Binding("f", "broker_flow", "Desk flow", show=False),
        Binding("h", "broker_history", "Desk history", show=False),
        Binding("v", "broker_jump_ticker", "Desk→ticker", show=False),
        Binding("b", "ticker_desks", "Ticker→desks", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

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
        ticker_desks_loader: Callable[[str], Any] | None = None,
        accum_controller: Any | None = None,
        preopen_controller: Any | None = None,
        accum_presenter: Any | None = None,
        preopen_presenter: Any | None = None,
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
        self._ticker_desks_loader = ticker_desks_loader
        self._accum_controller = accum_controller
        self._preopen_controller = preopen_controller
        self._accum_presenter = accum_presenter
        self._preopen_presenter = preopen_presenter

        self._sidebar_visible = True
        # shell | empty | accum | preopen | broker-list | detail | plan | loading | error
        self._stage = "shell"
        self._board_kind: BoardKind = "none"
        self._detail_return_stage: DetailReturnStage = "shell"
        self._broker_list_return: DetailReturnStage = "shell"
        self._broker_desk_code: str | None = None
        self._broker_page: str | None = None  # list|show|top|flow|history|None
        self._broker_jump_ticker: str | None = None
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
        self._plan_ticker: str = ""
        self._plan_result: str = ""
        self._plan_running: bool = False

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
                    yield DataTable(id="board-table")
                    yield Static("", id="evidence-strip")
                    yield Static(self._footer_hint(), id="board-footer")
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
                yield Static("enter   view", classes="side-line")
                yield Static("p       plan", classes="side-line")
                yield Static("r       refresh local", classes="side-line")
                yield Static("ctrl+b  sidebar", classes="side-line")
                yield Static("Online", classes="side-title")
                yield Static("Offline by default.", classes="side-line")
                yield Static("Fetch is explicit.", classes="side-line", id="side-online")
        yield Static(self._status_text(), id="status")

    def on_mount(self) -> None:
        table = self.query_one("#board-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = False
        table.display = False
        self.query_one("#evidence-strip", Static).display = False
        self._refresh_chrome()
        # Live cockpit: open on local accumulation board (not a design manifesto).
        # Still local-first — no network until explicit Fetch.
        if self._accum_controller is not None or self._accum_loader is not None:
            self._load_accum()
        else:
            self._stage = "shell"
            self._board_title = "Cockpit"
            self._meta = "no loader · Ctrl+P for commands"
            self._refresh_chrome()

    # ── chrome ─────────────────────────────────────────────

    def _mode_label(self) -> str:
        return f"● {self._mode}"

    def _status_text(self) -> str:
        return (
            f"Cockpit · {self._stage} · {self._focus_ticker}  ·  "
            f"{self._mode}  ·  {self._status_note}  ·  ai-saham tui"
        )

    def _footer_hint(self) -> str:
        if self._stage == "empty":
            return "ctrl+p → Fetch market data (explicit) · no invented rows"
        if self._stage == "accum":
            return (
                "↑↓ move · Enter view · p plan · r refresh · Ctrl+P  ·  "
                "ranked by Signal (not Accum) · Ctrl+P pre-open to switch board"
            )
        if self._stage == "preopen":
            return (
                "↑↓ move · Enter view · p plan · r refresh · Ctrl+P  ·  "
                "IEV snapshot board · Enter = present-only inspect"
            )
        if self._stage == "broker-list":
            return "↑↓ move · Enter desk home · esc back · Ctrl+P · view broker list"
        if self._stage == "ticker-desks":
            if any(getattr(r, "has_partial_netx", False) for r in self._broker_rows):
                return (
                    "↑↓ · Enter desk · esc ticker · "
                    "* NetX partial = sessions < window (value*(used/X))"
                )
            return (
                "↑↓ move · Enter desk home · esc → view ticker · Ctrl+P · "
                "tops day · Net3/5/7/10/20 stock sessions"
            )
        if self._stage == "detail" and self._broker_page in {
            "show",
            "top",
            "flow",
            "history",
        }:
            return (
                "↑↓ scroll · t top · f flow · h history · v view ticker · esc desk trail · Ctrl+P"
            )
        if self._stage == "detail" and self._status_note == "view ticker":
            return "↑↓/PgUp/PgDn scroll · b top desks · esc back · p plan · Ctrl+P"
        if self._stage == "detail":
            return "↑↓/PgUp/PgDn scroll · esc back · p plan · Ctrl+P"
        if self._stage == "plan":
            return "↑↓ scroll · esc back · p re-run · Ctrl+P · no broker order"
        return "Ctrl+P commands · ? help · q quit"

    def _shell_body(self) -> str:
        return (
            "[bold #e8e8e8]Starting cockpit…[/]\n\n"
            "Loading [bold]Screen · accumulation[/] from local cache.\n"
            "No network on open — Fetch is explicit via Ctrl+P.\n\n"
            "[dim]Ctrl+P commands · ? help · q quit[/]"
        )

    def _empty_body(self) -> str:
        return (
            "[bold #e8e8e8]No local market data[/]\n\n"
            "Cockpit is local-first. Nothing is on disk for this session,\n"
            "so screens cannot invent candidates.\n\n"
            "Online is available — [bold]only if you ask[/] via palette\n"
            "→ [bold]Fetch market data[/]\n\n"
            "[#9b8fb8]What this protects[/]\n"
            "· No silent network on open\n"
            "· Fetch is an explicit command, same as CLI\n"
            "· Empty cache refuses to invent rows"
        )

    def _refresh_chrome(self) -> None:
        self.query_one("#view-title", Static).update(self._board_title)
        self.query_one("#view-meta", Static).update(f"· {self._meta}")
        self.query_one("#mode-pill", Static).update(self._mode_label())
        self.query_one("#status", Static).update(self._status_text())
        self.query_one("#board-footer", Static).update(self._footer_hint())
        self.query_one("#side-mode", Static).update(f"Mode     {self._mode}")
        self.query_one("#side-focus", Static).update(
            "none selected"
            if self._focus_ticker == "—"
            else f"{self._focus_ticker} · Enter view · p plan"
        )

        body = self.query_one("#stage-body", Static)
        scroll = self.query_one("#stage-scroll", VerticalScroll)
        table = self.query_one("#board-table", DataTable)
        evidence = self.query_one("#evidence-strip", Static)

        if self._stage == "shell":
            scroll.display = True
            body.update(self._shell_body())
            table.display = False
            evidence.display = False
        elif self._stage == "empty":
            scroll.display = True
            body.update(self._empty_body())
            table.display = False
            evidence.display = False
            self.query_one("#side-cache", Static).update("Cache    empty")
        elif self._stage == "loading":
            scroll.display = True
            body.update(
                "[#d4b06a]Loading local board…[/]\n\n"
                f"{self._board_title}\n"
                "[dim]Reading SQLite cache · same use cases as CLI[/]"
            )
            table.display = False
            evidence.display = False
        elif self._stage == "error":
            scroll.display = True
            body.update(
                f"[#c97a72]Error[/]\n{self._error_text}\n\n[dim]r retry · Ctrl+P commands[/]"
            )
            table.display = False
            evidence.display = False
        elif self._stage == "detail":
            scroll.display = True
            body.update(self._detail_text)
            table.display = False
            evidence.display = False
            # Focus scroll so ↑↓ / wheel / PgUp/PgDn work on long view-ticker pages.
            scroll.focus()
        elif self._stage == "plan":
            scroll.display = True
            body.update(self._plan_body_text())
            table.display = False
            evidence.display = False
            scroll.focus()
        elif self._stage in {"broker-list", "ticker-desks"}:
            scroll.display = False
            table.display = True
            evidence.display = False
        elif self._stage in {"accum", "preopen"}:
            scroll.display = False
            table.display = True
            if self._evidence_text:
                evidence.display = True
                evidence.update(self._evidence_text)
            else:
                evidence.display = False

    # ── actions ────────────────────────────────────────────

    def action_command_palette(self) -> None:
        def _on_dismiss(command_id: str | None) -> None:
            if command_id:
                self._run_command(command_id)

        self.push_screen(CommandPalette(), _on_dismiss)

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
            # Desk trail: deep → show → list or ticker-desks.
            if self._stage == "detail" and self._broker_page in {"top", "flow", "history"}:
                if self._broker_desk_code:
                    self._open_broker_desk_show(
                        code=self._broker_desk_code,
                        entry=self._desk_entry,
                    )
                    return
            if self._stage == "detail" and self._broker_page == "show":
                self._view_from_desk = False
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
            and self._broker_page in {"show", "top", "flow", "history"}
        )

    def action_broker_top(self) -> None:
        if self._modal_blocks_board_keys() or not self._desk_hub_active():
            return
        self._open_broker_deep("top")

    def action_broker_flow(self) -> None:
        if self._modal_blocks_board_keys() or not self._desk_hub_active():
            return
        self._open_broker_deep("flow")

    def action_broker_history(self) -> None:
        if self._modal_blocks_board_keys() or not self._desk_hub_active():
            return
        self._open_broker_deep("history")

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

    def action_ticker_desks(self) -> None:
        """From view ticker: open top desks for this stock (CLI top-brokers)."""
        if self._modal_blocks_board_keys():
            return
        if self._stage != "detail" or self._status_note != "view ticker":
            return
        stock = str(self._focus_ticker or "").upper()
        if not stock or stock == "—":
            self.notify("No ticker focused", timeout=1.5)
            return
        self._open_ticker_desks(stock)

    def action_refresh_local(self) -> None:
        if self._modal_blocks_board_keys():
            return
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
        """Enter: board inspect, or desk home from broker-list / ticker-desks."""
        if self._modal_blocks_board_keys():
            return
        if self._stage == "broker-list":
            self._open_broker_desk_show(entry="broker-list")
            return
        if self._stage == "ticker-desks":
            self._open_broker_desk_show(entry="ticker-desks")
            return
        self._open_detail()

    def _modal_blocks_board_keys(self) -> bool:
        """True when a modal (palette/confirm/help) is on top — do not steal keys."""
        # screen_stack[0] is the main CockpitApp screen; anything above is a modal.
        return len(self.screen_stack) > 1

    def action_cursor_down(self) -> None:
        if self._modal_blocks_board_keys():
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
        self._row_index = min(len(self._rows) - 1, self._row_index + 1)
        self._sync_table_cursor()
        self._update_focus_from_row()

    def action_cursor_up(self) -> None:
        if self._modal_blocks_board_keys():
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
        Broker list / ticker desks: desk show (CLI view broker show).
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
        self._stage = "empty"
        self._board_title = "Screen · —"
        self._meta = "waiting on local data"
        self._mode = "no cache"
        self._focus_ticker = "—"
        self._rows = []
        self._status_note = "empty · fetch explicit"
        self._refresh_chrome()
        self.notify("Empty cache state", timeout=1.2)

    # ── accum / preopen load ───────────────────────────────

    def _load_accum(self) -> None:
        if self._accum_controller is None and self._accum_loader is None:
            self.notify("Screen accumulation — not wired (composition)", timeout=2.0)
            self._stage = "accum"
            self._board_title = "Screen · accumulation"
            self._meta = "loader not injected"
            self._rows = []
            self._refresh_chrome()
            return
        self._stage = "loading"
        self._board_title = "Screen · accumulation"
        self._meta = "local cache · recomputing"
        self._refresh_chrome()
        generation = 0
        if self._accum_controller is not None:
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
        self._stage = "loading"
        self._board_title = "Screen · pre-open"
        self._meta = "IEP / local · recomputing"
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
            self._show_empty()
            self._board_title = "Screen · accumulation"
            self._meta = "local · 0 candidates"
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
            self._stage = "empty"
            self._board_title = "Screen · pre-open"
            self._meta = "no IEP / empty local"
            self._mode = "local-first"
            self._rows = []
            self.query_one("#side-preopen", Static).update("Pre-open 0")
            self._refresh_chrome()
            return
        self._on_preopen_payload(state.payload)

    def _on_accum_payload(self, payload: Any) -> None:
        summary = ""
        self._board_kind = "accum"
        # Workflow result carries session + display-only MCE; projection fakes may not.
        self._effective_session = getattr(payload, "effective_session", None)
        self._market_context = getattr(payload, "market_context", None)
        if self._accum_presenter is not None:
            view = self._accum_presenter.present(payload)
            self._rows = list(view.rows)
            self._meta = view.meta
            summary = getattr(view, "summary", "") or ""
            self._board_summary = summary
            self.query_one("#side-accum", Static).update(f"Accum    {len(self._rows)}")
            self.query_one("#side-cache", Static).update(f"Cache    {view.cache_label}")
        else:
            self._rows = list(payload) if payload else []
            self._meta = f"local · {len(self._rows)} names"
            self._board_summary = ""
        self._board_title = "Screen · accumulation"
        self._mode = "local-first"
        self._row_index = 0
        self._status_note = summary if summary else f"{len(self._rows)} rows"
        if not self._rows:
            self._show_empty()
            self._board_title = "Screen · accumulation"
            self._meta = self._meta or "local · 0 candidates"
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
        note = summary if summary else f"{len(self._rows)} candidates"
        self.notify(f"Accumulation · {note}", timeout=2.5)

    def _on_preopen_payload(self, payload: Any) -> None:
        self._board_kind = "preopen"
        self._preopen_snapshot_date = str(getattr(payload, "snapshot_date", "") or "")
        raw_warn = getattr(payload, "warnings", ()) or ()
        self._preopen_warnings = tuple(str(w) for w in raw_warn)
        if self._preopen_presenter is not None:
            view = self._preopen_presenter.present(payload)
            self._rows = list(view.rows)
            self._meta = view.meta
            self.query_one("#side-preopen", Static).update(f"Pre-open {len(self._rows)}")
            self.query_one("#side-cache", Static).update(f"Cache    {view.cache_label}")
        else:
            self._rows = list(payload) if payload else []
            self._meta = f"pre-open · {len(self._rows)}"
        self._board_title = "Screen · pre-open"
        self._mode = "local-first"
        self._row_index = 0
        self._status_note = f"{len(self._rows)} graded"
        if not self._rows:
            self._stage = "empty"
            self._meta = self._meta or "no IEP candidates"
            self._refresh_chrome()
            self.notify("Pre-open · no local IEP candidates", timeout=2.0)
            return
        self._stage = "preopen"
        self._focus_ticker = self._rows[0].ticker
        self._render_board_table()
        self._update_preopen_evidence()
        self._refresh_chrome()
        self.query_one("#board-table", DataTable).focus()
        self.notify(f"Pre-open · {len(self._rows)} graded (local snapshot)", timeout=2.0)

    def _render_board_table(self) -> None:
        table = self.query_one("#board-table", DataTable)
        table.clear(columns=True)
        if self._stage == "broker-list":
            # Desk radar: DayNet + Net5 + buy-streak (+ Δ1) from cache
            table.add_columns("Code", "Type", "AsOf", "DayNet", "Net5", "Stk", "Δ1", "#", "Top")
            for row in self._broker_rows:
                table.add_row(
                    str(getattr(row, "code", "?")),
                    str(getattr(row, "type_label", "—")),
                    str(getattr(row, "as_of", "—") or "—"),
                    str(getattr(row, "day_net", "—") or "—"),
                    str(getattr(row, "net5", "—") or "—"),
                    str(getattr(row, "streak", "—") or "—"),
                    str(getattr(row, "delta1", "—") or "—"),
                    str(getattr(row, "tickers", "—") or "—"),
                    str(getattr(row, "top_buy", "—") or "—"),
                )
            if self._broker_rows:
                table.move_cursor(row=self._broker_row_index, animate=False)
            return
        if self._stage == "ticker-desks":
            # Ranked by latest tops; NetX = stock×desk last X sessions (no name col)
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
                    str(getattr(row, "code", "?")),
                    str(getattr(row, "type_label", "—")),
                    str(getattr(row, "role", "—")),
                    str(getattr(row, "as_of", "—") or "—"),
                    str(getattr(row, "day_net", "—") or "—"),
                    str(getattr(row, "net3", "—") or "—"),
                    str(getattr(row, "net5", "—") or "—"),
                    str(getattr(row, "net7", "—") or "—"),
                    str(getattr(row, "net10", "—") or "—"),
                    str(getattr(row, "net20", "—") or "—"),
                    str(getattr(row, "streak", "—") or "—"),
                    str(getattr(row, "delta1", "—") or "—"),
                )
            if self._broker_rows:
                table.move_cursor(row=self._broker_row_index, animate=False)
            return
        is_preopen = self._stage == "preopen" or self._board_kind == "preopen"
        if is_preopen:
            table.add_columns("Tkr", "IEP", "Δ%", "IEV", "NCP", "ΔIEV", "Grd", "Risk")
            for row in self._rows:
                table.add_row(
                    row.ticker,
                    row.iep,
                    row.delta_pct,
                    row.iev,
                    row.ncp,
                    row.delta_iev,
                    row.grade,
                    row.risk,
                )
        else:
            # Option B desk board — ADR-043 Signal/Accum vocabulary
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
                table.add_row(
                    row.ticker,
                    getattr(row, "signal", "—"),
                    getattr(row, "accum", "—"),
                    getattr(row, "action", "—"),
                    getattr(row, "phase", "—"),
                    getattr(row, "streak", "—"),
                    getattr(row, "rsi", "—"),
                    getattr(row, "net_pct", "—"),
                    getattr(row, "disc_pct", "—"),
                    getattr(row, "price", "—"),
                    getattr(row, "gate", "—"),
                )
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
        self.query_one("#side-cache", Static).update(f"Cache    {focus.lag_label}")
        self.query_one("#side-focus", Static).update(focus.focus_sidebar)
        if focus.lag_label and focus.lag_label != "—":
            # Keep summary in status; append lag posture when present
            base = self._board_summary or self._status_note
            if "LAG" in focus.lag_label or "ALIGNED" in focus.lag_label:
                self._status_note = f"{base} · {focus.lag_label}" if base else focus.lag_label
            self.query_one("#status", Static).update(self._status_text())

    def _remember_return_stage(self) -> None:
        if self._stage in {"accum", "preopen"}:
            self._detail_return_stage = self._stage  # type: ignore[assignment]
        elif self._board_kind in {"accum", "preopen"}:
            self._detail_return_stage = self._board_kind  # type: ignore[assignment]
        elif self._stage not in {"detail", "plan"}:
            self._detail_return_stage = "shell"

    def _open_detail(self) -> None:
        """Board Enter: present-only engine inspect (screen row object)."""
        if self._stage == "empty" or self._focus_ticker in {"—", ""}:
            self.notify("Nothing to inspect — run a screen first", timeout=1.5)
            return
        if not self._rows and self._stage != "detail":
            self.notify("No row focused", timeout=1.5)
            return
        ticker = self._focus_ticker
        row = self._rows[self._row_index] if self._rows else None
        self._remember_return_stage()

        base = self._format_row_detail(ticker, row)
        self._detail_text = base
        self._stage = "detail"
        if self._is_accum_row(row):
            self._board_title = f"Screen · accum · {ticker}"
            self._meta = "inspect · present-only · same object as board"
        elif self._is_preopen_row(row):
            self._board_title = f"Screen · pre-open · {ticker}"
            self._meta = "inspect · present-only · same object as board"
        else:
            self._board_title = f"Inspect · {ticker}"
            self._meta = "present-only · board row"
        self._status_note = "inspect"
        self._refresh_chrome()

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
        self._board_title = f"View · ticker show · {ticker}"
        self._meta = "CLI parity · cache-only dashboard"
        self._status_note = "view ticker"
        self._refresh_chrome()
        self._execute_view_ticker(ticker)

    def _open_view_broker_list(self) -> None:
        """Ctrl+P View broker: tracked desk list → Enter opens desk show."""
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
        self._meta = "CLI parity · saham view broker list"
        self._status_note = "view broker"
        self._refresh_chrome()
        self._execute_broker_list()

    def _open_ticker_desks(self, stock: str) -> None:
        """From view ticker: stock → top desks (CLI view ticker top-brokers)."""
        stock = str(stock or "").upper()
        if not stock or stock == "—":
            self.notify("No ticker focused", timeout=1.5)
            return
        self._ticker_desks_stock = stock
        self._view_from_desk = False
        self._broker_desk_code = None
        self._broker_page = None
        self._desk_entry = None
        self._stage = "loading"
        self._board_title = f"View · ticker desks · {stock}"
        self._meta = "CLI parity · saham view ticker top-brokers"
        self._status_note = "view ticker desks"
        self._refresh_chrome()
        self._execute_ticker_desks(stock)

    def _restore_ticker_desks_table(self) -> None:
        """Return from desk show to the stock→desks table without re-fetch."""
        stock = self._ticker_desks_stock or "—"
        self._broker_page = None
        self._broker_desk_code = None
        self._view_from_desk = False
        self._desk_entry = "ticker-desks"
        self._stage = "ticker-desks"
        self._plan_running = False
        self._board_title = f"View · ticker desks · {stock}"
        n = len(self._broker_rows)
        self._meta = f"{n} desks · {stock} · Enter home · esc view ticker"
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
            self._board_title = "View · broker list"
            self._meta = "no tracked desks in config"
            self._refresh_chrome()
            self.notify("View broker · no tracked desks", timeout=2.0)
            return
        self._stage = "broker-list"
        self._focus_ticker = str(getattr(self._broker_rows[0], "code", "—"))
        self._board_title = "View · broker list"
        with_data = sum(1 for r in self._broker_rows if getattr(r, "has_data", True))
        self._meta = (
            f"{len(self._broker_rows)} desks · {with_data} with flow · Enter home · sorted |Net5|"
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
        self._stage = "ticker-desks"
        self._board_title = f"View · ticker desks · {stock}"
        as_of_s = str(as_of) if as_of else "—"
        note_s = str(note) if note else "top buyers/sellers"
        if not self._broker_rows:
            self._meta = f"as of {as_of_s} · {note_s} · 0 desks"
            self._status_note = "view ticker desks"
            self._focus_ticker = stock
            self._render_board_table()
            self._refresh_chrome()
            self.query_one("#board-table", DataTable).focus()
            self.notify(f"Ticker desks · {stock} · empty", timeout=2.0)
            return
        self._focus_ticker = str(getattr(self._broker_rows[0], "code", "—"))
        self._meta = f"as of {as_of_s} · {len(self._broker_rows)} desks · {note_s} · Enter home"
        if any(getattr(r, "has_partial_netx", False) for r in self._broker_rows):
            # Keep warning visible even if note was truncated in chrome width.
            if "partial" not in self._meta.lower():
                self._meta = f"{self._meta} · * NetX partial (used/X)"
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
        self._stage = "loading"
        self._board_title = f"View · broker show · {code}"
        self._meta = f"desk home · t/f/h deep · v stock · {esc_hint}"
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
        }
        self._stage = "loading"
        self._board_title = titles.get(page, f"View · broker · {code}")
        self._meta = f"desk deep · esc home · CLI view broker {page}"
        self._status_note = f"view broker {page}"
        self._refresh_chrome()
        self._execute_broker_deep(code, page)

    @work(thread=True, exclusive=True, group="detail")
    def _execute_broker_show(self, code: str) -> None:
        try:
            payload = (
                self._broker_show_loader(code) if self._broker_show_loader is not None else None
            )
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
            if not text.strip():
                text = (
                    f"[bold]{code}[/]\n\n"
                    "[dim]no broker_daily_flow for this desk · fetch broker data[/]"
                )
            esc_line = "  esc desks" if self._desk_entry == "ticker-desks" else "  esc list"
            actions = (
                "\n\n[#9b8fb8]Actions (TUI)[/]\n"
                "  t top-stocks · f flow · h history\n"
                "  v view ticker (top buy stock)\n"
                f"{esc_line}\n"
            )
            header = (
                f"[bold #e8e8e8]View · broker show · {code}[/]\n"
                f"[dim]same job as: saham view broker show {code} · local cache[/]\n\n"
            )
            dispatch_if_active(
                self,
                self._on_broker_page_ready,
                code,
                "show",
                header + text + actions,
                jump,
            )
        except Exception as exc:
            dispatch_if_active(
                self,
                self._on_broker_page_ready,
                code,
                "show",
                f"[bold]View · broker show · {code}[/]\n\n[dim]error: {exc}[/]",
                None,
            )

    @work(thread=True, exclusive=True, group="detail")
    def _execute_broker_deep(self, code: str, page: str) -> None:
        try:
            loader = {
                "top": self._broker_top_loader,
                "flow": self._broker_flow_loader,
                "history": self._broker_history_loader,
            }.get(page)
            text = str(loader(code) if loader is not None else "") if loader else ""
            if not text.strip():
                text = f"[bold]{code}[/]\n\n[dim]no data · loader missing or empty[/]"
            titles = {
                "top": "top-stocks",
                "flow": "flow",
                "history": "history",
            }
            label = titles.get(page, page)
            header = (
                f"[bold #e8e8e8]View · broker {label} · {code}[/]\n"
                f"[dim]same job as: saham view broker {label} {code} · local cache[/]\n\n"
            )
            footer = (
                "\n\n[#9b8fb8]Actions[/]\n  t/f/h switch deep · v view ticker · esc desk home\n"
            )
            dispatch_if_active(
                self,
                self._on_broker_page_ready,
                code,
                page,
                header + text + footer,
                self._broker_jump_ticker,
            )
        except Exception as exc:
            dispatch_if_active(
                self,
                self._on_broker_page_ready,
                code,
                page,
                f"[bold]View · broker {page} · {code}[/]\n\n[dim]error: {exc}[/]",
                None,
            )

    def _on_broker_page_ready(
        self,
        code: str,
        page: str,
        text: str,
        jump_ticker: str | None,
    ) -> None:
        # Drop stale worker results when user already moved on.
        if self._broker_desk_code != code or self._broker_page != page:
            return
        if jump_ticker is not None:
            self._broker_jump_ticker = jump_ticker
        self._detail_text = text
        self._stage = "detail"
        titles = {
            "show": f"View · broker show · {code}",
            "top": f"View · broker top-stocks · {code}",
            "flow": f"View · broker flow · {code}",
            "history": f"View · broker history · {code}",
        }
        self._board_title = titles.get(page, f"View · broker · {code}")
        self._meta = "CLI parity · cache-only · esc trail"
        self._status_note = f"view broker {page}"
        self._refresh_chrome()

    @work(thread=True, exclusive=True, group="detail")
    def _execute_view_ticker(self, ticker: str) -> None:
        try:
            if self._ticker_detail_loader is not None:
                text = str(self._ticker_detail_loader(ticker) or "")
            else:
                text = f"[bold]{ticker}[/]\n\n[dim]view ticker loader not wired (composition)[/]"
            if not text.strip():
                text = f"[bold]{ticker}[/]\n\n[dim]empty dashboard[/]"
            header = (
                f"[bold #e8e8e8]View · ticker show · {ticker}[/]\n"
                f"[dim]same job as: saham view ticker show {ticker} · local cache[/]\n\n"
            )
            dispatch_if_active(self, self._on_view_ticker_ready, ticker, header + text)
        except Exception as exc:
            dispatch_if_active(
                self,
                self._on_view_ticker_ready,
                ticker,
                f"[bold]View · ticker show · {ticker}[/]\n\n[dim]error: {exc}[/]",
            )

    def _on_view_ticker_ready(self, ticker: str, text: str) -> None:
        actions = "\n\n[#9b8fb8]Actions (TUI)[/]\n  b top desks for this stock\n" + (
            "  esc → desk home\n" if self._view_from_desk else "  esc back\n"
        )
        if "Actions (TUI)" not in text:
            text = text + actions
        self._detail_text = text
        self._stage = "detail"
        self._board_title = f"View · ticker show · {ticker}"
        if self._view_from_desk:
            self._meta = "from desk · b desks · esc → desk home · cache-only"
            self._broker_page = None  # not a desk page; trail via _view_from_desk
        else:
            self._meta = "CLI parity · b top desks · cache-only · esc back"
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
        return all(hasattr(row, k) for k in ("iep", "grade", "risk", "delta_pct"))

    def _format_row_detail(self, ticker: str, row: Any) -> str:
        if row is None:
            return f"[bold]{ticker}[/]\n\n[dim]No row payload[/]"

        if self._is_accum_row(row) or self._board_kind == "accum":
            if self._is_accum_row(row):
                from src.adapters.tui.presenters.accum_engine_inspect_presenter import (
                    present_accum_engine_inspect,
                )

                view = present_accum_engine_inspect(
                    row,
                    rank=self._row_index + 1,
                    total=max(len(self._rows), 1),
                    board_summary=self._board_summary,
                    effective_session=self._effective_session,
                    market_context=self._market_context,
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
            ("iep", "IEP"),
            ("delta_pct", "Δ%"),
            ("iev", "IEV"),
            ("ncp", "NCP"),
            ("grade", "Grade"),
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
        self._plan_running = True
        self._stage = "plan"
        self._board_title = f"Plan · {ticker} · structure"
        self._meta = "structure desk · local · no broker order"
        self._status_note = "plan running"
        self._refresh_chrome()

        if self._plan_runner is None:
            self._plan_running = False
            self._plan_result = "no plan runner wired · stub only"
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
            running=self._plan_running,
        )
        return view.text

    @work(thread=True, exclusive=True, group="plan")
    def _execute_plan(self, ticker: str) -> None:
        try:
            result = self._plan_runner(ticker) if self._plan_runner else None
            msg = f"Plan swing · {ticker}"
            if result is not None:
                summary = getattr(result, "summary", None) or str(result)[:120]
                msg = f"{summary}"
            dispatch_if_active(self, self._on_plan_done, ticker, msg)
        except Exception as exc:
            dispatch_if_active(self, self._on_plan_done, ticker, f"error: {exc}")

    def _on_plan_done(self, ticker: str, msg: str) -> None:
        self._plan_running = False
        self._plan_result = msg
        self._status_note = "plan done"
        # Stay on plan stage so the page is the result surface (variant A).
        if self._stage == "plan" and self._plan_ticker == ticker:
            self._meta = "structure result · no broker order"
            self._refresh_chrome()
        self.notify(f"Plan · {ticker} · {msg}", timeout=2.5)

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
                self.notify("Fetch not wired — use CLI: saham fetch market", timeout=2.5)
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
        self.query_one("#side-online", Static).update("Last fetch ok · now local")
        self.query_one("#side-cache", Static).update("Cache    refreshed")
        self.notify("Fetch complete · reloading accumulation", timeout=2.0)
        self._load_accum()


def run_tui() -> None:
    """Construct and run the optional cockpit from its composition root."""
    from src.adapters.tui.composition import create_tui_app

    create_tui_app().run()
