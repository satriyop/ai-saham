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

from src.adapters.tui.theme import OC, bake_css

# Design tokens — brass = nav keys · peach fill = is-on
_BRASS = OC.brass
_LABEL = OC.text_dim
_ON_INK = OC.sel_text
_DIM_KEY = OC.brass
_DIM_LAB = OC.text_mute


def format_chip_markup(
    word: str,
    *,
    power_key: str | None = None,
    is_on: bool = False,
    dim: bool = False,
) -> str:
    """Leading bold ``[k]`` + product word (design keycap-in-chip).

    Brass when idle; dark ink when is-on (peach fill). Dim mutes both.

    Important: Textual/Rich markup treats ``[b]`` as a style tag. Escape the
    opening bracket so the keycap is literal: ``\\[b]`` → visible ``[b]``.
    """
    word = (word or "").strip() or "—"
    k = (power_key or "").strip().lower()
    if not k:
        if dim:
            return f"[{_DIM_LAB}]{word}[/]"
        if is_on:
            return f"[bold {_ON_INK}]{word}[/]"
        return word
    # Literal keycap for Textual Content markup (do not use raw [k])
    keycap = f"\\[{k}]"
    if dim:
        return f"[bold {_DIM_KEY}]{keycap}[/] [{_DIM_LAB}]{word}[/]"
    if is_on:
        # Dark on peach — not brass-on-peach
        return f"[bold {_ON_INK}]{keycap}[/] [{_ON_INK}]{word}[/]"
    return f"[bold {_BRASS}]{keycap}[/] [{_LABEL}]{word}[/]"


class FlagChip(Static):
    """Mono pill chip: available · is-on · is-dim · warn · brass keycap."""

    DEFAULT_CSS = bake_css("""
    FlagChip {
        /* Uniform OpenCode pills: fixed row height so labels + borders align */
        width: auto;
        min-width: 9;
        height: 3;
        color: $oc_text;
        background: $oc_bg_elevated;
        border: solid $oc_hairline_strong;
        padding: 0 1;
        margin: 0 1 0 0;
        content-align: center middle;
        text-style: none;
    }
    FlagChip:hover {
        color: $oc_text_bright;
        border: solid $oc_text_mute;
        background: $oc_scalar_track;
    }
    FlagChip:focus {
        border: solid $oc_peach;
        color: $oc_text_bright;
    }
    FlagChip.is-on {
        color: $oc_sel_text;
        background: $oc_peach;
        border: solid $oc_peach;
        text-style: none;
    }
    FlagChip.is-dim {
        color: $oc_dim;
        background: $oc_track_inactive;
        border: solid $oc_hairline_strong;
    }
    FlagChip.warn {
        color: $oc_brass;
        border: solid $oc_warn_bg;
        background: $oc_warn_bg;
    }
    FlagChip.warn.is-on {
        color: $oc_sel_text;
        background: $oc_brass;
        border: solid $oc_brass;
        text-style: none;
    }
    /* Context sub-chips (e.g. fin [y] period): not painted outside parent job */
    FlagChip.is-context-off {
        display: none !important;
        visibility: hidden;
        width: 0 !important;
        min-width: 0 !important;
        max-width: 0 !important;
        height: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
    }
    """)

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

    @property
    def word(self) -> str:
        """Product / mode word (no keycap)."""
        return self._word

    def set_word(self, word: str) -> None:
        """Update product/mode word and repaint keycap (binary toggle flip label)."""
        self._word = (word or "").strip() or "—"
        self._label = self._word
        self.set_chip_state(
            available=self._available,
            expanded=self._expanded,
            warn=self.has_class("warn"),
        )

    def set_context_visible(self, visible: bool) -> None:
        """Show/hide job-local sub-chips (fin period). Hidden = not painted, not dim.

        Design: hide/unmount context — never permanent dim-on-bar for other jobs.
        """
        if visible:
            self.remove_class("is-context-off")
            self.display = True
            self.can_focus = True
        else:
            self.add_class("is-context-off")
            self.display = False
            self.can_focus = False
            self.set_chip_state(available=False, expanded=False)

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
            # Dim only when still painted; context-off chips stay fully hidden
            if not self.has_class("is-context-off"):
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
