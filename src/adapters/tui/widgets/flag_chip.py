"""Shared OpenCode flag-chip control (present-only expand affordance).

Click toggles named detail panels. Never invents Action authority.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual.message import Message
from textual.widgets import Static


class FlagChip(Static):
    """Mono pill chip: available · is-on · is-dim · warn."""

    DEFAULT_CSS = """
    FlagChip {
        width: auto;
        height: 1;
        color: #8a8a8a;
        background: #141414;
        border: solid #1c1c1c;
        padding: 0 1;
        margin-right: 1;
    }
    FlagChip:hover {
        color: #e8e8e8;
        border: solid #333333;
    }
    FlagChip:focus {
        border: solid #c9a68a;
        color: #e8e8e8;
    }
    FlagChip.is-on {
        color: #0b0b0b;
        background: #c9a68a;
        border: solid #c9a68a;
        text-style: bold;
    }
    FlagChip.is-dim {
        color: #3a3a3a;
        background: #101010;
        border: solid #141414;
    }
    FlagChip.warn {
        color: #d4b06a;
        border: solid #3a3220;
        background: #1a1810;
    }
    FlagChip.warn.is-on {
        color: #0b0b0b;
        background: #d4b06a;
        border: solid #d4b06a;
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
        self._available = True

    def set_chip_state(
        self,
        *,
        available: bool,
        expanded: bool,
        warn: bool = False,
    ) -> None:
        self._available = available
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
