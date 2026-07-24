"""
Shared response contract for `saham screen` discovery commands.

Mirrors the view-ticker envelope vocabulary so CLI and future TUI Discover
share one metadata language.

Layer: Application
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class ScreenSubjectKind(str, Enum):
    SCREEN = "screen"
    WATCHLIST = "watchlist"
    UNIVERSE = "universe"


class ScreenResultStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    MISSING = "missing"
    ERROR = "error"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    return str(value)


def build_screen_envelope(
    *,
    verb: str,
    status: ScreenResultStatus,
    data: Any,
    subject_id: str | None = None,
    subject_kind: ScreenSubjectKind = ScreenSubjectKind.SCREEN,
    as_of: date | datetime | None = None,
    source: str | None = None,
    scope: str | None = None,
    scope_note: str | None = None,
    fetch_hint: str | None = None,
    window_days: int | None = None,
) -> dict[str, Any]:
    """Strict metadata envelope for screen discovery JSON output."""
    as_of_str: str | None
    if as_of is None:
        as_of_str = None
    elif isinstance(as_of, datetime):
        as_of_str = as_of.isoformat()
    else:
        as_of_str = as_of.isoformat()

    subject = {
        "kind": subject_kind.value,
        "id": (subject_id or verb).upper(),
    }
    return {
        "subject": subject,
        "verb": verb,
        "as_of": as_of_str,
        "window": {"days": window_days} if window_days is not None else None,
        "source": source,
        "scope": scope,
        "scope_note": scope_note,
        "status": status.value,
        "fetch_hint": fetch_hint,
        "data": _json_safe(data),
    }


def default_screen_fetch_hint(*, universe: str | None = None) -> str:
    if universe:
        return f"saham fetch market --universe {universe}"
    return "saham fetch market"


def missing_screen_message(
    *,
    what: str,
    name: str | None = None,
    source: str | None = None,
    fetch_hint: str | None = None,
) -> str:
    label = f"{what} '{name}'" if name else what
    lines = [f"No cached {label}."]
    if source:
        lines.append(f"Source: {source}")
    if fetch_hint:
        lines.append(f"Run: {fetch_hint}")
    return "\n".join(lines)
