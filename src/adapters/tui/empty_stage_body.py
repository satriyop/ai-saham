"""Honest empty-stage posters for the TUI cockpit (design: tui-session-health.html).

Distinct empty / lag / ready / zero-candidate posters. Pure adapter presentation.

Layer: Adapter
"""

from __future__ import annotations

from src.adapters.tui.theme import OC


def format_empty_stage_body(
    *,
    cache_status: str | None,
    board_title: str = "",
    meta: str = "",
    board_kind: str = "none",
    next_step: str = "",
) -> str:
    """Build empty-stage main body from health + board context.

    Rules:
    - cache_status empty → true "no local market data" + fetch cue
    - 0-candidate / accum empty with ready|lag|unknown → do not claim no data
    - pre-open empty → IEP-specific honesty
    - broker empty → config/tracked desks honesty
    """
    status = (cache_status or "").strip().lower() or None
    title = (board_title or "").strip().lower()
    meta_l = (meta or "").strip().lower()
    kind = (board_kind or "none").strip().lower()
    fetch_cue = (next_step or "").strip() or "Ctrl+P · Fetch market data (explicit)"

    if _is_broker_empty(title, meta_l, kind):
        return _broker_empty()

    if _is_preopen_empty(title, meta_l, kind):
        return _preopen_empty(status=status, fetch_cue=fetch_cue)

    if _is_zero_candidate_screen(title, meta_l, kind):
        return _zero_candidate_body(status=status, fetch_cue=fetch_cue, kind="accumulation")

    # True empty cache (empty-demo, no disk, health empty)
    if status == "empty":
        return _true_empty_cache(fetch_cue=fetch_cue)

    # Explicit lag poster when health lags and stage is generic empty
    if status == "lag":
        return _lag_poster(fetch_cue=fetch_cue)

    # Health ready but generic empty stage
    if status == "ready":
        return _ready_poster(fetch_cue=fetch_cue)

    if status == "unknown":
        return _unknown_health(fetch_cue=fetch_cue)

    # Loader missing / no status — conservative empty-cache copy
    return _true_empty_cache(fetch_cue=fetch_cue)


def _is_broker_empty(title: str, meta: str, kind: str) -> bool:
    if "broker" in title or "desk" in title:
        return True
    if "tracked desk" in meta or "no tracked" in meta:
        return True
    return kind in {"broker", "broker-list"}


def _is_preopen_empty(title: str, meta: str, kind: str) -> bool:
    if kind == "preopen":
        return True
    if "pre-open" in title or "preopen" in title:
        return True
    if "iep" in meta or "iev" in meta:
        return True
    return False


def _is_zero_candidate_screen(title: str, meta: str, kind: str) -> bool:
    if kind == "accum":
        return True
    if "0 candidate" in meta or "0 names" in meta:
        return True
    if "accumulation" in title and ("0" in meta or "empty" in meta or "local" in meta):
        return True
    return False


def _true_empty_cache(*, fetch_cue: str) -> str:
    return (
        f"[bold {OC.coral}]SESSION HEALTH · EMPTY[/]\n"
        f"[bold {OC.text_bright}]No local market data[/]\n\n"
        "Nothing on disk for this session. Screens refuse to invent candidates.\n"
        "Cockpit refuses to invent rows when cache is empty.\n"
        "Online only if you ask.\n\n"
        f"[{OC.brass}]Next[/]  [bold]{fetch_cue}[/]\n\n"
        f"[{OC.text_mute}]What this protects[/]\n"
        "· No silent network on open\n"
        "· Fetch is explicit · same as CLI\n"
        "· Empty cache refuses invented rows"
    )


def _lag_poster(*, fetch_cue: str) -> str:
    return (
        f"[bold {OC.brass}]POSTER · LAG[/]\n"
        f"[bold {OC.text_bright}]Local cache lagging[/]\n\n"
        "Candle and broker dates disagree or trail the session.\n"
        "Board may still show rows later — do not pretend ready.\n\n"
        f"[{OC.brass}]Next[/]  Explicit fetch only if deliberate · {fetch_cue}\n"
        "· Or continue when a board loads from local cache\n\n"
        "[dim]Local-first · fetch remains explicit · never automatic on open[/]"
    )


def _ready_poster(*, fetch_cue: str) -> str:
    return (
        f"[bold {OC.mint}]POSTER · READY[/]\n"
        f"[bold {OC.text_bright}]Local cache ready[/]\n\n"
        "Dates present and aligned on the Session rail.\n"
        "This empty stage means no board row set is open right now —\n"
        "not that SQLite is empty.\n\n"
        f"[{OC.brass}]Try[/]\n"
        "· s a · Screen accumulation\n"
        "· s p · Screen pre-open\n"
        "· r · Refresh local when a board is open\n"
        f"· Fetch stays explicit: {fetch_cue}\n\n"
        "[dim]Local-first · no silent network[/]"
    )


def _local_present_no_rows(*, status: str, fetch_cue: str) -> str:
    """Legacy alias used by tests of ready/lag generic empty — keep poster tones."""
    if status == "lag":
        return _lag_poster(fetch_cue=fetch_cue)
    return _ready_poster(fetch_cue=fetch_cue)


def _zero_candidate_body(*, status: str | None, fetch_cue: str, kind: str) -> str:
    if status == "empty":
        return _true_empty_cache(fetch_cue=fetch_cue)

    lag_line = ""
    if status == "lag":
        lag_line = (
            f"Session rail shows [bold {OC.brass}]LAG[/] — data may be stale; "
            "fetch only if deliberate.\n\n"
        )
    elif status in {"ready", None, "unknown"}:
        lag_line = "Local cache is available (see Session · Cache rail).\n\n"

    return (
        f"[bold {OC.blue}]POSTER · ZERO CANDIDATES[/]\n"
        f"[bold {OC.text_bright}]No {kind} candidates[/]\n\n"
        f"{lag_line}"
        "The screen ran against local data and returned [bold]0 names[/].\n"
        "That is a real result — not missing market data and not invented rows.\n\n"
        f"[{OC.brass}]Try[/]\n"
        "· r refresh local board (same cache)\n"
        "· Ctrl+P · other screens (pre-open / view)\n"
        f"· Fetch only if cache is empty/lag: {fetch_cue}\n\n"
        "[dim]Filters and score thresholds may exclude everyone today.[/]"
    )


def _preopen_empty(*, status: str | None, fetch_cue: str) -> str:
    if status == "empty":
        return (
            f"[bold {OC.coral}]POSTER · NO IEV SNAPSHOT[/]\n"
            f"[bold {OC.text_bright}]No pre-open snapshot[/]\n\n"
            "Local IEV / NCP data is missing. Pre-open cannot invent IEP rows.\n\n"
            f"[{OC.brass}]Next[/]  explicit fetch iev (CLI/palette) · {fetch_cue}\n\n"
            "[dim]Never silent network on open.[/]"
        )
    return (
        f"[bold {OC.blue}]POSTER · NO IEP CANDIDATES[/]\n"
        f"[bold {OC.text_bright}]No IEP candidates[/]\n\n"
        "Pre-open read local IEV snapshot and found nothing to grade,\n"
        "or the snapshot has no names for this session.\n\n"
        f"[{OC.brass}]Try[/]\n"
        "· r refresh pre-open from cache\n"
        "· Explicit [bold]fetch iev[/] if snapshot is missing/stale\n"
        "· s a · Screen accumulation for cash-session board\n\n"
        "[dim]Local-first · no invented auction rows.[/]"
    )


def _broker_empty() -> str:
    return (
        f"[bold {OC.purple}]POSTER · NO DESKS[/]\n"
        f"[bold {OC.text_bright}]No broker desks to list[/]\n\n"
        "View broker has no tracked desks in config, or none matched filters.\n"
        "This is not the same as empty market candles.\n\n"
        f"[{OC.brass}]Try[/]\n"
        "· Check broker tracking config\n"
        "· v t · view ticker · b desks from a stock\n"
        "· Explicit fetch broker if flow tables are empty"
    )


def _unknown_health(*, fetch_cue: str) -> str:
    return (
        f"[bold {OC.text_mute}]POSTER · HEALTH UNKNOWN[/]\n"
        f"[bold {OC.text_bright}]Empty board · cache health unknown[/]\n\n"
        "Could not read local candle/broker dates. Refusing to invent rows.\n\n"
        f"[{OC.brass}]Next[/]  {fetch_cue} · or check DB path / lock\n\n"
        "[dim]Local-first · no silent network.[/]"
    )
