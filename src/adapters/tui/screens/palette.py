"""OpenCode-style command palette (Ctrl+P).

Layer: Adapter
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from src.adapters.tui.commands import CockpitCommand, filter_commands


class CommandPalette(ModalScreen[str | None]):
    """Searchable command list. Dismisses with command_id or None."""

    BINDINGS = [
        Binding("escape", "dismiss_palette", "Close", show=False, priority=True),
        Binding("up", "move_up", "Up", show=False, priority=True),
        Binding("down", "move_down", "Down", show=False, priority=True),
        # priority so app-level Enter (view ticker) cannot steal run.
        Binding("enter", "run_selected", "Run", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._filtered: list[CockpitCommand] = filter_commands("")
        self._index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="palette-card", classes="dialog-card"):
            with Horizontal(id="palette-head"):
                yield Static("Commands", id="palette-title")
                yield Static("esc", id="palette-esc")
            yield Input(placeholder="Search commands…", id="palette-input")
            yield Static("", id="palette-list")
            with Horizontal(id="palette-foot"):
                yield Static("↑↓ navigate  ↵ run  esc close")
                yield Static("no tabs · palette is the nav", classes="dim")

    def on_mount(self) -> None:
        self._render_list()
        self.query_one("#palette-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "palette-input":
            return
        self._filtered = filter_commands(event.value)
        self._index = 0
        self._render_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter while search is focused must run the selected command.

        Without this, Textual routes Enter to the Input and the palette never
        dismisses with a command_id (board looks like palette 'does nothing').
        """
        if event.input.id != "palette-input":
            return
        event.stop()
        self.action_run_selected()

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
        self.dismiss(self._filtered[self._index].command_id)

    def _render_list(self) -> None:
        if not self._filtered:
            self.query_one("#palette-list", Static).update("[dim]No matches[/dim]")
            return
        lines: list[str] = []
        last_section = ""
        for i, cmd in enumerate(self._filtered):
            if cmd.section != last_section:
                lines.append(f"[#9b8fb8]{cmd.section}[/]")
                last_section = cmd.section
            marker = ">" if i == self._index else " "
            sc = f"  [dim]{cmd.shortcut}[/]" if cmd.shortcut else ""
            show_desc = bool(cmd.description and i == self._index)
            desc = f"\n    [dim]{cmd.description}[/]" if show_desc else ""
            if i == self._index:
                lines.append(f"[bold #1a120c on #c9a68a]{marker} {cmd.label}{sc}[/]{desc}")
            else:
                lines.append(f"{marker} {cmd.label}{sc}")
        self.query_one("#palette-list", Static).update("\n".join(lines))
