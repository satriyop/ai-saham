"""OpenCode-style daily cockpit Textual app (optional TUI adapter).

Phase 0 shell: layout B chrome + stub command palette. Data stages land in
later phases. Visual contract: docs/design/tui-cockpit-opencode.md

Layer: Adapter
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class CommandPalette(ModalScreen[str | None]):
    """Minimal Ctrl+P palette (OpenCode shape). Selection returns command id."""

    BINDINGS = [
        Binding("escape", "dismiss_palette", "Close", show=False),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "run_selected", "Run", show=False),
    ]

    # (section, command_id, label, shortcut)
    COMMANDS: tuple[tuple[str, str, str, str], ...] = (
        ("Suggested", "screen-accum", "Screen accumulation", "s a"),
        ("Suggested", "screen-preopen", "Screen pre-open", "s p"),
        ("Suggested", "plan-swing", "Plan swing", "p"),
        ("Daily", "view-ticker", "View ticker", "enter"),
        ("Data", "fetch", "Fetch market data", ""),
        ("Data", "empty-demo", "Show empty cache state", ""),
        ("Session", "toggle-sidebar", "Hide sidebar", "ctrl+b"),
        ("Session", "help", "Help", "?"),
    )

    def __init__(self) -> None:
        super().__init__()
        self._filtered: list[tuple[str, str, str, str]] = list(self.COMMANDS)
        self._index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-card"):
            with Horizontal(id="palette-head"):
                yield Static("Commands", id="palette-title")
                yield Static("esc", id="palette-esc")
            yield Input(placeholder="Search commands…", id="palette-input")
            yield Static("", id="palette-list")
            with Horizontal(id="palette-foot"):
                yield Static("↑↓ navigate  ↵ run  esc close", id="palette-hints")
                yield Static("no tabs · palette is the nav", id="palette-tag")

    def on_mount(self) -> None:
        self._render_list()
        self.query_one("#palette-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "palette-input":
            return
        q = event.value.strip().lower()
        if not q:
            self._filtered = list(self.COMMANDS)
        else:
            self._filtered = [
                c
                for c in self.COMMANDS
                if q in c[1].lower() or q in c[2].lower() or q in c[0].lower()
            ]
        self._index = 0
        self._render_list()

    def action_dismiss_palette(self) -> None:
        self.dismiss(None)

    def action_move_up(self) -> None:
        if not self._filtered:
            return
        self._index = max(0, self._index - 1)
        self._render_list()

    def action_move_down(self) -> None:
        if not self._filtered:
            return
        self._index = min(len(self._filtered) - 1, self._index + 1)
        self._render_list()

    def action_run_selected(self) -> None:
        if not self._filtered:
            return
        self.dismiss(self._filtered[self._index][1])

    def _render_list(self) -> None:
        if not self._filtered:
            self.query_one("#palette-list", Static).update("[dim]No matches[/dim]")
            return
        lines: list[str] = []
        last_section = ""
        for i, (section, _cid, label, shortcut) in enumerate(self._filtered):
            if section != last_section:
                lines.append(f"[#9b8fb8]{section}[/]")
                last_section = section
            marker = ">" if i == self._index else " "
            sc = f"  [dim]{shortcut}[/]" if shortcut else ""
            if i == self._index:
                lines.append(f"[bold #1a120c on #c9a68a]{marker} {label}{sc}[/]")
            else:
                lines.append(f"{marker} {label}{sc}")
        self.query_one("#palette-list", Static).update("\n".join(lines))


class CockpitApp(App[None]):
    """Daily cockpit shell — layout B (main stage + context sidebar + status)."""

    TITLE = "ai-saham"
    SUB_TITLE = "cockpit"

    BINDINGS = [
        Binding("ctrl+p", "command_palette", "Commands", show=True, priority=True),
        Binding("ctrl+b", "toggle_sidebar", "Sidebar", show=False),
        Binding("question_mark", "show_help_toast", "Help", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    CSS = """
    Screen {
        background: #0b0b0b;
        color: #d8d8d8;
    }

    #workspace {
        width: 100%;
        height: 1fr;
    }

    #main {
        width: 1fr;
        height: 100%;
        border-right: solid #1c1c1c;
        padding: 1 2;
    }

    #main-header {
        height: 2;
        margin-bottom: 1;
    }

    #view-title {
        text-style: bold;
        color: #e8e8e8;
    }

    #view-meta {
        color: #555555;
    }

    #stage {
        height: 1fr;
        color: #7a7a7a;
    }

    #sidebar {
        width: 28;
        height: 100%;
        background: #0e0e0e;
        padding: 1 1;
    }

    #sidebar.hidden {
        width: 0;
        padding: 0;
        border: none;
        display: none;
    }

    .side-title {
        text-style: bold;
        color: #d8d8d8;
        margin-top: 1;
    }

    .side-title.first {
        margin-top: 0;
    }

    .side-line {
        color: #555555;
    }

    #status {
        height: 1;
        background: #090909;
        color: #555555;
        padding: 0 1;
        border-top: solid #1c1c1c;
    }

    CommandPalette {
        align: center middle;
        background: rgba(0, 0, 0, 0.45);
    }

    #palette-card {
        width: 64;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        background: #1a1a1a;
        border: solid #2a2a2a;
        padding: 1 1;
    }

    #palette-head {
        height: 1;
        margin-bottom: 1;
    }

    #palette-title {
        width: 1fr;
        color: #7a7a7a;
        text-style: bold;
    }

    #palette-esc {
        width: auto;
        color: #555555;
        text-align: right;
    }

    #palette-input {
        margin-bottom: 1;
        background: #121212;
        border: solid #252525;
        color: #d8d8d8;
    }

    #palette-list {
        height: auto;
        max-height: 20;
        margin-bottom: 1;
        color: #d8d8d8;
    }

    #palette-foot {
        height: 1;
        border-top: solid #252525;
        padding-top: 1;
    }

    #palette-hints {
        width: 1fr;
        color: #555555;
    }

    #palette-tag {
        width: auto;
        color: #555555;
        text-align: right;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._sidebar_visible = True
        self._stage_name = "shell"
        self._focus_ticker = "—"
        self._mode = "local-first"

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace"):
            with Vertical(id="main"):
                with Vertical(id="main-header"):
                    yield Static("Cockpit · shell", id="view-title")
                    yield Static(
                        "· Phase 0 — press Ctrl+P · Enter will view (later phases)",
                        id="view-meta",
                    )
                yield Static(self._stage_body(), id="stage")
            with Vertical(id="sidebar"):
                yield Static("Session", classes="side-title first")
                yield Static("Market   IDX", classes="side-line")
                yield Static("Mode     local-first", classes="side-line", id="side-mode")
                yield Static("Cache    —", classes="side-line", id="side-cache")
                yield Static("Focus", classes="side-title")
                yield Static("none selected", classes="side-line", id="side-focus")
                yield Static("Keys", classes="side-title")
                yield Static("ctrl+p  commands", classes="side-line")
                yield Static("ctrl+b  sidebar", classes="side-line")
                yield Static("q       quit", classes="side-line")
                yield Static("Online", classes="side-title")
                yield Static("Offline by default.", classes="side-line")
                yield Static("Fetch is explicit (palette).", classes="side-line")
        yield Static(self._status_text(), id="status")

    def _stage_body(self) -> str:
        if self._stage_name == "empty":
            return (
                "[bold #e8e8e8]No local market data[/]\n\n"
                "Cockpit is local-first. Nothing is loaded yet.\n"
                "Online is available — only if you ask via palette.\n\n"
                "[#9b8fb8]What this protects[/]\n"
                "· No silent network on open\n"
                "· Fetch is an explicit command, same as CLI\n"
                "· Empty cache refuses to invent rows\n\n"
                "[dim]Phases 2+ wire real screen boards here.[/]"
            )
        return (
            "[bold #e8e8e8]Daily cockpit[/]  [dim]OpenCode layout B[/]\n\n"
            "Navigation is the command palette — [bold]no scenario tabs[/].\n\n"
            "  [bold]Ctrl+P[/]  open commands\n"
            "  [bold]Enter[/]   view ticker (later)\n"
            "  [bold]p[/]       plan swing — deliberate confirm (later)\n"
            "  [bold]Ctrl+B[/]  toggle sidebar\n"
            "  [bold]q[/]       quit\n\n"
            "[#9b8fb8]Suggested (when wired)[/]\n"
            "  Screen accumulation · Screen pre-open · Plan swing\n\n"
            "[dim]Design: docs/design/tui-cockpit-opencode.md[/]\n"
            "[dim]ADR-051 clean break from multi-route research TUI[/]"
        )

    def _status_text(self) -> str:
        return (
            f"Cockpit · {self._stage_name} · {self._focus_ticker}  ·  "
            f"{self._mode}  ·  ctrl+p commands  ·  ai-saham tui"
        )

    def _refresh_chrome(self) -> None:
        self.query_one("#stage", Static).update(self._stage_body())
        self.query_one("#status", Static).update(self._status_text())
        title = {
            "shell": "Cockpit · shell",
            "empty": "Screen · —",
            "accum": "Screen · accumulation",
            "preopen": "Screen · pre-open",
        }.get(self._stage_name, f"Cockpit · {self._stage_name}")
        self.query_one("#view-title", Static).update(title)
        self.query_one("#side-mode", Static).update(f"Mode     {self._mode}")

    def action_command_palette(self) -> None:
        def _on_dismiss(command_id: str | None) -> None:
            if command_id:
                self._run_command(command_id)

        self.push_screen(CommandPalette(), _on_dismiss)

    def action_toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        sidebar = self.query_one("#sidebar")
        sidebar.set_class(not self._sidebar_visible, "hidden")
        self.notify(
            "Sidebar hidden" if not self._sidebar_visible else "Sidebar shown",
            timeout=1.5,
        )

    def action_show_help_toast(self) -> None:
        self.notify("Ctrl+P commands · Ctrl+B sidebar · q quit", timeout=2.5)

    def action_quit(self) -> None:
        self.workers.cancel_all()
        self.exit()

    def _run_command(self, command_id: str) -> None:
        if command_id == "toggle-sidebar":
            self.action_toggle_sidebar()
            return
        if command_id == "help":
            self.action_show_help_toast()
            return
        if command_id == "empty-demo":
            self._stage_name = "empty"
            self._focus_ticker = "—"
            self._mode = "no cache"
            self._refresh_chrome()
            self.query_one("#side-cache", Static).update("Cache    empty")
            self.query_one("#side-focus", Static).update("none — fetch first")
            self.notify("Empty cache state", timeout=1.5)
            return
        if command_id in {"screen-accum", "screen-preopen", "plan-swing", "view-ticker", "fetch"}:
            # Phase 0: acknowledge without inventing data or going online.
            labels = {
                "screen-accum": "Screen accumulation — Phase 2",
                "screen-preopen": "Screen pre-open — Phase 3",
                "plan-swing": "Plan swing — Phase 4 (deliberate confirm)",
                "view-ticker": "View ticker — Phase 2 (Enter=view)",
                "fetch": "Fetch market data — Phase 4 (explicit online)",
            }
            self.notify(labels[command_id], timeout=2.0)
            if command_id == "screen-accum":
                self._stage_name = "accum"
                self._refresh_chrome()
            elif command_id == "screen-preopen":
                self._stage_name = "preopen"
                self._refresh_chrome()
            return
        self.notify(f"{command_id} · not wired", timeout=1.5)


def run_tui() -> None:
    """Construct and run the optional cockpit from its composition root."""
    from src.adapters.tui.composition import create_tui_app

    create_tui_app().run()
