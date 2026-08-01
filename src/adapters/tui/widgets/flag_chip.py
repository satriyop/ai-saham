"""Shared OpenCode flag-chip control (Chip bar contract).

Navigation: mouse click · Tab focus · Enter/Space activate.
Power letter paint: bold brass ``[k]`` + mute label (design lock).
Never invents Action authority. Use inside :class:`ChipBar` when possible.

Layer: Adapter (Textual widget)
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import Static

# Design tokens — brass = nav keys · peach fill = is-on
_BRASS = "#d4b06a"
_LABEL = "#a0a0a0"
_ON_INK = "#1a120c"
_DIM_KEY = "#6b5a3a"
_DIM_LAB = "#555555"


def format_chip_markup(
    word: str,
    *,
    power_key: str | None = None,
    is_on: bool = False,
    dim: bool = False,
) -> str:
    """Leading bold ``[k]`` + product word (design keycap-in-chip).

    Brass when idle; dark ink when is-on (peach fill). Dim mutes both.
    """
    word = (word or "").strip() or "—"
    k = (power_key or "").strip().lower()
    if not k:
        if dim:
            return f"[{_DIM_LAB}]{word}[/]"
        if is_on:
            return f"[bold {_ON_INK}]{word}[/]"
        return word
    keycap = f"[{k}]"
    if dim:
        return f"[bold {_DIM_KEY}]{keycap}[/] [{_DIM_LAB}]{word}[/]"
    if is_on:
        # Dark on peach — not brass-on-peach
        return f"[bold {_ON_INK}]{keycap}[/] [{_ON_INK}]{word}[/]"
    return f"[bold {_BRASS}]{keycap}[/] [{_LABEL}]{word}[/]"


class FlagChip(Static):
    """Mono pill chip: available · is-on · is-dim · warn · brass keycap."""

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
        text-style: none;
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
        text-style: none;
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
        power_key: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        # ``label`` is the product word only (e.g. brokers). Optional power_key → [b].
        # If label already starts with ``[x] ``, strip for word and infer power.
        word, inferred = _split_keycap_label(label)
        pk = (power_key or inferred or "").strip().lower() or None
        self.flag_key = flag_key
        self._word = word
        self._power_key = pk
        self._label = word  # product word (tests / callers)
        self._available = True
        self._expanded = False
        markup = format_chip_markup(word, power_key=pk, is_on=False, dim=False)
        super().__init__(markup, id=id, classes=classes)

    @property
    def power_key(self) -> str | None:
        return self._power_key

    def set_chip_state(
        self,
        *,
        available: bool,
        expanded: bool,
        warn: bool = False,
    ) -> None:
        self._available = available
        self._expanded = expanded
        # Re-assert keycap markup every paint (never blank chips)
        self.update(
            format_chip_markup(
                self._word,
                power_key=self._power_key,
                is_on=bool(expanded and available),
                dim=not available,
            )
        )
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

    def on_click(self, event: events.Click) -> None:
        """Activate chip; stop bubble so stage remounts cannot steal the click."""
        event.stop()
        event.prevent_default()
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
        # Focus chip so detail paint does not yank focus to scroll mid-toolbar use
        try:
            self.focus()
        except Exception:
            pass
        self.post_message(self.Selected(self.flag_key))


def _split_keycap_label(label: str) -> tuple[str, str | None]:
    """Parse ``[d] detail`` → (detail, d); plain word → (word, None)."""
    s = (label or "").strip()
    if len(s) >= 3 and s[0] == "[" and "]" in s[1:3]:
        # [x] rest
        close = s.find("]")
        if close == 2 and close + 1 < len(s):
            key = s[1:close]
            rest = s[close + 1 :].strip()
            if key and rest:
                return rest, key.lower()
    return s, None


def apply_flag_chip_state(
    chip: FlagChip,
    *,
    available: bool,
    expanded: bool,
    warn: bool = False,
) -> None:
    chip.set_chip_state(available=available, expanded=expanded, warn=warn)
