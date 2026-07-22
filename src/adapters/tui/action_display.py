"""Presentation-only decoration of canonical setup actions with status glyphs.

Layer: Adapter

The canonical ENTER/WATCH/AVOID vocabulary is owned by the domain
``SetupAction`` enum. This module maps those domain values to display glyphs
without redefining the vocabulary, so the TUI never becomes a second source of
truth for action names.
"""

from __future__ import annotations

from src.domain.value_objects.trade_setup import SetupAction

_ACTION_GLYPH: dict[SetupAction, str] = {
    SetupAction.ENTER: "▲",  # ▲ bullish / actionable
    SetupAction.WATCH: "◆",  # ◆ caution / monitor
    SetupAction.AVOID: "▼",  # ▼ bearish / avoid
}


def decorate_action(action_value: str | None) -> str:
    """Return the action value prefixed with its status glyph, or ``-`` if empty.

    Unknown values (e.g. BLOCKED_* or non-canonical text) render as-is so the
    display never hides an action it does not have a glyph for.
    """
    if not action_value:
        return "-"
    try:
        member = SetupAction(str(action_value))
    except ValueError:
        return str(action_value)
    glyph = _ACTION_GLYPH.get(member)
    return f"{glyph} {action_value}" if glyph else str(action_value)
