"""Canonical TradeSetup Action labels for multi-surface display.

Single home for Action vocabulary strings used by CLI/TUI presentation.
Adapters must import these names rather than re-literalizing Action tokens,
so the TUI cannot silently invent a parallel Action vocabulary (architecture
boundary tests scan TUI sources for raw Action string constants).

Layer: Adapter (shared presentation)
"""

from __future__ import annotations

# Production Action values (domain TradeAction / TradeSetup.action).
ACTION_ENTER = "ENTER"
ACTION_WATCH = "WATCH"
ACTION_AVOID = "AVOID"
ACTION_BLOCKED_STRUCTURAL = "BLOCKED_STRUCTURAL"
ACTION_BLOCKED_EXECUTION = "BLOCKED_EXECUTION"

# Informal / legacy synonyms that still color like Action in desks.
ACTION_BUY = "BUY"
ACTION_HOLD = "HOLD"
ACTION_SELL = "SELL"
ACTION_BLOCK = "BLOCK"

ENTER_LIKE = frozenset({ACTION_ENTER, ACTION_BUY})
WATCH_LIKE = frozenset({ACTION_WATCH, ACTION_HOLD})
AVOID_LIKE = frozenset({ACTION_AVOID, ACTION_BLOCK, ACTION_SELL})

# Spaced tokens for scanning operator-facing browse text for invented Actions.
ACTION_SCAN_TOKENS: tuple[str, ...] = (
    f" {ACTION_ENTER} ",
    f" {ACTION_WATCH} ",
    f" {ACTION_AVOID} ",
    f"{ACTION_ENTER}/",
    f"{ACTION_WATCH}/",
    f"{ACTION_AVOID}/",
)

CANONICAL_ACTIONS: frozenset[str] = frozenset(
    {
        ACTION_ENTER,
        ACTION_WATCH,
        ACTION_AVOID,
        ACTION_BLOCKED_STRUCTURAL,
        ACTION_BLOCKED_EXECUTION,
    }
)
