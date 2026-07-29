"""Pure decisions for TUI board load/refresh chrome.

Layer: Adapter (no IO)
"""

from __future__ import annotations


def should_blank_board_for_load(
    *,
    has_visible_rows: bool,
    current_stage: str,
    current_board_kind: str,
    target_board_kind: str,
) -> bool:
    """Return True when load should hide the board and show a blank loading stage.

    When the operator already has a ready board of the same kind, keep rows
    visible and only mark recomputing (generation tracker still invalidates
    stale workers).
    """
    if not has_visible_rows:
        return True
    if current_board_kind != target_board_kind:
        return True
    # Keep prior board while reloading the same surface.
    if current_stage in {"accum", "preopen", "loading"}:
        return False
    return True


def recomputing_status_note(*, row_count: int, summary: str = "") -> str:
    """Status strip text while a local recompute is in flight."""
    base = summary.strip() if summary else (f"{row_count} rows" if row_count else "board")
    return f"recomputing… · {base}"


def snapshot_freshness_note(*, as_of: str, captured_at: str, universe: str) -> str:
    """Mandatory cue that restored board is a prior local snapshot, not live."""
    as_of_part = as_of.strip() if as_of.strip() else "—"
    captured = captured_at.strip() if captured_at.strip() else "—"
    uni = universe.strip() if universe.strip() else "local"
    return f"snapshot · as of {as_of_part} · saved {captured} · {uni}"
