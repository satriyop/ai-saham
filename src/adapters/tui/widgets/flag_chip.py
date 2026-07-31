"""Shared OpenCode flag-chip control (present-only expand affordance).

Click toggles named detail panels. Never invents Action authority.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import Static


class FlagChip(Static):
    """Mono pill chip: available · is-on · is-dim · warn."""

    DEFAULT_CSS = """
    FlagChip {
        /* Uniform OpenCode pills: fixed row height so labels + borders align */
        width: auto;
        min-width: 9;
        height: 3;
        color: #c8c8c8;
        background: #141414;
        border: solid #2a2a2a;
        padding: 0 1;
        margin: 0 1 0 0;
        content-align: center middle;
        text-style: none;
    }
    FlagChip:hover {
        color: #e8e8e8;
        border: solid #555555;
        background: #1a1a1a;
    }
    FlagChip:focus {
        border: solid #c9a68a;
        color: #e8e8e8;
    }
    FlagChip.is-on {
        color: #1a120c;
        background: #c9a68a;
        border: solid #c9a68a;
        text-style: bold;
    }
    FlagChip.is-dim {
        color: #6b6b6b;
        background: #121212;
        border: solid #2a2a2a;
    }
    FlagChip.warn {
        color: #d4b06a;
        border: solid #3a3220;
        background: #1a1810;
    }
    FlagChip.warn.is-on {
        color: #1a120c;
        background: #d4b06a;
        border: solid #d4b06a;
        text-style: bold;
    }
    """

    can_focus = True

    class Selected(Message):
        """Posted when operator activates an available chip."""

        def __init__(self, flag_key: str) -> None:
            self.flag_key = flag_key
            super().__init__()

    def __init__(
        self,
        flag_key: str,
        label: str,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(label, id=id, classes=classes)
        self.flag_key = flag_key
        self._label = label
        self._available = True

    def set_chip_state(
        self,
        *,
        available: bool,
        expanded: bool,
        warn: bool = False,
    ) -> None:
        self._available = available
        # Re-assert label every paint (never blank chips)
        self.update(self._label)
        self.remove_class("is-on")
        self.remove_class("is-dim")
        self.remove_class("warn")
        if warn:
            self.add_class("warn")
        if not available:
            self.add_class("is-dim")
            return
        if expanded:
            self.add_class("is-on")

    def on_click(self) -> None:
        self._activate()

    def on_key(self, event: events.Key) -> None:
        """Keyboard activate (Enter / Space) — same path as click."""
        if event.key in {"enter", "space"}:
            event.stop()
            event.prevent_default()
            self._activate()

    def _activate(self) -> None:
        if not self._available:
            return
        self.post_message(self.Selected(self.flag_key))


def apply_flag_chip_state(
    chip: FlagChip,
    *,
    available: bool,
    expanded: bool,
    warn: bool = False,
) -> None:
    chip.set_chip_state(available=available, expanded=expanded, warn=warn)
