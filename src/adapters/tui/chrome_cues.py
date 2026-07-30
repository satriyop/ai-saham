"""Operator-facing chrome strings for snapshot board and in-flight loads.

Pure adapter presentation helpers — no I/O, no policy.

Layer: Adapter
"""

from __future__ import annotations


def snapshot_accum_footer(*, freshness: str = "") -> str:
    """Footer when accum board is last-run snapshot (no candidate source).

    Enter opens limited judge; j or r is the full-desk escape hatch.
    """
    note = (freshness or "").strip() or "prior local run"
    return (
        "snapshot board · Enter = limited judge · "
        "j re-judge or r live for full desk · p plan · Ctrl+P  ·  "
        f"{note}"
    )


def snapshot_accum_meta(*, base_meta: str = "", freshness: str = "") -> str:
    """Meta strip: keep board facts, add limited-judge honesty."""
    base = (base_meta or "").strip()
    fresh = (freshness or "").strip()
    cue = "snapshot · Enter limited judge · j/r full desk"
    parts = [p for p in (base, cue, fresh) if p]
    # Avoid duplicate "snapshot" spam if base already mentions it
    out: list[str] = []
    seen_snap = False
    for p in parts:
        pl = p.lower()
        if "snapshot" in pl and "limited" not in pl and seen_snap:
            continue
        if "snapshot" in pl:
            seen_snap = True
        out.append(p)
    return " · ".join(out) if out else cue


def snapshot_mode_label() -> str:
    return "● snapshot · limited judge"


def broker_list_loading_body() -> str:
    """Main stage body while view-broker list worker is in flight."""
    return (
        "[#d4b06a]Loading broker desk list…[/]\n\n"
        "View · broker list (CLI: saham view broker list)\n\n"
        "Reading tracked desks from [bold]local cache[/] — not hung.\n"
        "Local cache only (recent sessions · no network).\n\n"
        "[dim]When ready: ↑↓ · Enter desk home · esc back[/]"
    )


def broker_list_loading_footer() -> str:
    return "loading broker list… · local cache · same job as CLI view broker list · wait"


def broker_list_loading_meta() -> str:
    return "loading tracked desks · local cache · not hung"


def is_broker_list_loading(*, stage: str, board_title: str = "", status_note: str = "") -> bool:
    if stage != "loading":
        return False
    title = (board_title or "").lower()
    note = (status_note or "").lower()
    if "broker list" in title or "view · broker list" in title:
        return True
    if note in {"view broker", "view broker list", "loading broker list"}:
        return True
    return "broker" in title and "list" in title


def loading_stage_body(
    *,
    board_title: str = "",
    status_note: str = "",
    stage: str = "loading",
) -> str:
    """Pick loading body copy from chrome context."""
    if is_broker_list_loading(stage=stage, board_title=board_title, status_note=status_note):
        return broker_list_loading_body()
    title = (board_title or "Local board").strip() or "Local board"
    return (
        f"[#d4b06a]Loading local board…[/]\n\n"
        f"{title}\n"
        "[dim]Reading SQLite cache · same use cases as CLI[/]"
    )
