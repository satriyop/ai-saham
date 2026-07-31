"""Session health poster model (structured hierarchy for HealthPosterDesk).

Layer: Adapter
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthPosterModel:
    kind: str  # empty | lag | ready | zero | preopen | broker | unknown
    kicker: str
    title: str
    body_lines: tuple[str, ...]
    next_cue: str
    why_lines: tuple[str, ...]
    footer: str


def build_health_poster_model(
    *,
    cache_status: str | None,
    board_title: str = "",
    meta: str = "",
    board_kind: str = "none",
    next_step: str = "",
) -> HealthPosterModel:
    """Map empty-stage context to poster hierarchy (same rules as empty_stage_body)."""
    from src.adapters.tui import empty_stage_body as esb

    status = (cache_status or "").strip().lower() or None
    title = (board_title or "").strip().lower()
    meta_l = (meta or "").strip().lower()
    kind = (board_kind or "none").strip().lower()
    fetch_cue = (next_step or "").strip() or "Ctrl+P · Fetch market data (explicit)"

    if esb._is_broker_empty(title, meta_l, kind):
        return HealthPosterModel(
            kind="broker",
            kicker="SESSION HEALTH · DESKS",
            title="No tracked desks",
            body_lines=(
                "Broker list has nothing to show.",
                "Track desks or fetch broker flow first.",
            ),
            next_cue=fetch_cue,
            why_lines=("Local-first · no invented desks", "Fetch is explicit"),
            footer="Ctrl+P · esc · offline by default",
        )
    if esb._is_preopen_empty(title, meta_l, kind):
        if status == "empty":
            return HealthPosterModel(
                kind="preopen",
                kicker="SESSION HEALTH · PRE-OPEN",
                title="No IEV snapshot",
                body_lines=("Pre-open needs a local IEV/NCP snapshot.",),
                next_cue=fetch_cue,
                why_lines=("No silent network", "Snapshot path only"),
                footer="Ctrl+P · esc",
            )
        return HealthPosterModel(
            kind="preopen",
            kicker="SESSION HEALTH · PRE-OPEN",
            title="No IEP candidates",
            body_lines=("Local snapshot present · zero graded names.",),
            next_cue=fetch_cue,
            why_lines=("Honest empty board", "Not inventing IEP rows"),
            footer="Ctrl+P · esc",
        )
    if esb._is_zero_candidate_screen(title, meta_l, kind):
        return HealthPosterModel(
            kind="zero",
            kicker="SESSION HEALTH · ZERO",
            title="Zero candidates",
            body_lines=(
                "Local cache can be ready while the board has no names.",
                "Filters or window may exclude all rows.",
            ),
            next_cue=fetch_cue,
            why_lines=("0 rows ≠ empty cache", "Ready/lag health still distinct"),
            footer="r refresh · Ctrl+P · esc",
        )
    if status == "empty":
        return HealthPosterModel(
            kind="empty",
            kicker="SESSION HEALTH · EMPTY",
            title="No local market data",
            body_lines=(
                "Nothing on disk for this session.",
                "Screens refuse to invent candidates.",
                "Online only if you ask.",
            ),
            next_cue=fetch_cue,
            why_lines=(
                "No silent network on open",
                "Fetch is explicit · same as CLI",
                "Empty cache refuses invented rows",
            ),
            footer="Ctrl+P · fetch · esc",
        )
    if status == "lag":
        return HealthPosterModel(
            kind="lag",
            kicker="SESSION HEALTH · LAG",
            title="Local data is lagging",
            body_lines=("Cache exists but is behind the session clock.",),
            next_cue=fetch_cue,
            why_lines=("Lag is not empty", "Refresh is explicit"),
            footer="r refresh · Ctrl+P",
        )
    if status == "ready":
        return HealthPosterModel(
            kind="ready",
            kicker="SESSION HEALTH · READY",
            title="Local cache ready",
            body_lines=("Disk looks ready · board may still be empty for this view.",),
            next_cue=fetch_cue,
            why_lines=("Ready health ≠ board rows",),
            footer="Ctrl+P · open a screen",
        )
    return HealthPosterModel(
        kind="unknown",
        kicker="SESSION HEALTH · UNKNOWN",
        title="Cache health unclear",
        body_lines=("Could not classify local cache status.",),
        next_cue=fetch_cue,
        why_lines=("Conservative empty handling",),
        footer="Ctrl+P · esc",
    )
