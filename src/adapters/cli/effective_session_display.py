"""Shared CLI helpers for effective-market-session transparency.

Layer: Adapter (parse/format only). Resolution policy stays in
``EffectiveMarketSessionResolver``.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

import typer


class _EffectiveSessionLike(Protocol):
    analysis_as_of: date | None
    latest_completed_session: date | None
    is_eod_pending: bool

    def to_dict(self) -> dict[str, Any]: ...


def parse_as_of_option(raw: str | None) -> date | None:
    """Parse ``--as-of YYYY-MM-DD``; fail closed on invalid input."""
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        typer.echo(
            f"[error] Invalid --as-of: {raw} (expected YYYY-MM-DD)",
            err=True,
        )
        raise typer.Exit(1)


def format_effective_session_label(session: _EffectiveSessionLike) -> str:
    """Human label: ``2026-07-23 (settled)`` or ``2026-07-24 (live · EOD pending)``."""
    day = session.analysis_as_of or session.latest_completed_session
    date_str = day.isoformat() if day is not None else "unknown"
    if session.is_eod_pending:
        return f"{date_str} (live · EOD pending)"
    return f"{date_str} (settled)"


def format_effective_session_line(session: _EffectiveSessionLike) -> str:
    return f"Effective session: {format_effective_session_label(session)}"


def effective_session_to_json(
    session: _EffectiveSessionLike | None,
) -> dict[str, Any] | None:
    if session is None:
        return None
    return session.to_dict()
