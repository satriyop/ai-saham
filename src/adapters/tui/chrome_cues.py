"""Operator-facing chrome strings for snapshot board and in-flight loads.

Pure adapter presentation helpers — no I/O, no policy.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.tui.theme import OC


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


def accum_source_badge_text(*, board_source: str, recomputing: bool = False) -> str:
    """Operator badge above accum board (mock ``src-badge``). Empty = hide."""
    src = (board_source or "none").strip().lower()
    if recomputing and src == "snapshot":
        return "snapshot · refreshing live…"
    if src == "snapshot":
        return "snapshot · limited judge until j/r"
    if src == "live":
        return "live · full present-only judge"
    return ""


def accum_source_badge_kind(*, board_source: str) -> str:
    """CSS kind: snap | live | hide."""
    src = (board_source or "none").strip().lower()
    if src == "snapshot":
        return "snap"
    if src == "live":
        return "live"
    return "hide"


def broker_list_title() -> str:
    """Tracked-desk radar (View broker)."""
    return "View · broker list"


def ticker_desks_title(stock: str) -> str:
    """Stock → top desks trail (from ticker brokers chip / b)."""
    s = (stock or "—").strip().upper() or "—"
    return f"View · desks · {s}"


def broker_radar_meta(
    *,
    desk_count: int,
    from_stock: str | None = None,
    with_flow: int | None = None,
    as_of: str | None = None,
    note: str | None = None,
    has_partial_netx: bool = False,
) -> str:
    """Operator meta for broker list or stock desks — no chip jargon.

    ``from_stock`` set → stock-scoped desks; else tracked radar.
    ``has_partial_netx`` → thin multi-session Net windows honesty.
    """
    parts: list[str] = []
    if as_of:
        parts.append(f"as of {as_of}")
    parts.append(f"{desk_count} desks")
    if from_stock:
        parts.append("top brokers")
    else:
        if with_flow is not None:
            parts.append(f"{with_flow} with flow")
        parts.append("tracked")
    if note and str(note).strip():
        n = str(note).strip()
        # Skip note fragments that only repeat partial honesty
        if "partial" not in n.lower():
            parts.append(n)
    parts.append("Enter home")
    if has_partial_netx:
        parts.append("thin NetX (partial sessions)")
    return " · ".join(parts)


def broker_list_loading_body() -> str:
    """Main stage body while view-broker list worker is in flight."""
    return (
        f"[{OC.brass}]Loading broker desk list…[/]\n\n"
        "View · broker list\n\n"
        "Reading tracked desks from [bold]local cache[/] — not hung.\n"
        "Local cache only (recent sessions · no network).\n\n"
        "[dim]When ready: ↑↓ · Enter desk home · esc back[/]"
    )


def broker_list_loading_footer() -> str:
    return "loading broker list… · local cache · wait"


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


def should_keep_board_during_loading(
    *,
    stage: str,
    board_kind: str = "",
    status_note: str = "",
    board_title: str = "",
    has_rows: bool = False,
) -> bool:
    """Whether loading may leave the accum/preopen DataTable visible.

    **Yes** only for same-surface board recompute (status contains recomput…).
    **No** for instrument navigations (view ticker jobs, broker show/deep, desks):
    unmasking the board under a chip click steals the click → accidental Judge.
    """
    if stage != "loading" or not has_rows:
        return False
    kind = (board_kind or "").strip().lower()
    if kind not in {"accum", "preopen"}:
        return False
    note = (status_note or "").strip().lower()
    title = (board_title or "").strip().lower()
    # Explicit instrument / browse surfaces — never keep board
    if note.startswith("view ticker") or note.startswith("view broker"):
        return False
    if "loading ticker" in note or "loading broker" in note:
        return False
    if "ticker desk" in title or "broker show" in title or "broker top" in title:
        return False
    if "broker flow" in title or "broker history" in title or "broker calendar" in title:
        return False
    if "ticker desks" in title or "broker list" in title:
        return False
    # Same-surface board recompute only
    if "recomput" in note:
        return True
    return False


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
    note = (status_note or "").strip().lower()
    if note.startswith("view ticker") or "ticker" in title:
        return (
            f"[{OC.brass}]Loading…[/]\n\n{title}\n[dim]Local cache · ticker surface · not hung[/]"
        )
    if note.startswith("view broker") or "broker" in title:
        return (
            f"[{OC.brass}]Loading…[/]\n\n{title}\n[dim]Local cache · broker surface · not hung[/]"
        )
    return f"[{OC.brass}]Loading local board…[/]\n\n{title}\n[dim]Reading local cache · not hung[/]"
