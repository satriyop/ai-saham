"""
Shared response contract for stock-axis `view ticker` deep-dives.

Layer: Application
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class ViewSubjectKind(str, Enum):
    TICKER = "ticker"
    DESK = "desk"


class ViewResultStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    MISSING = "missing"


@dataclass(frozen=True)
class ViewSubject:
    kind: ViewSubjectKind
    id: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "id": self.id}


@dataclass(frozen=True)
class ViewWindow:
    days: int | None = None
    from_date: date | None = None
    to_date: date | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "days": self.days,
            "from_date": self.from_date.isoformat() if self.from_date else None,
            "to_date": self.to_date.isoformat() if self.to_date else None,
        }


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


def build_view_envelope(
    *,
    subject_id: str,
    verb: str,
    status: ViewResultStatus,
    data: Any,
    as_of: date | None = None,
    window: ViewWindow | None = None,
    source: str | None = None,
    scope: str | None = None,
    scope_note: str | None = None,
    fetch_hint: str | None = None,
    subject_kind: ViewSubjectKind = ViewSubjectKind.TICKER,
) -> dict[str, Any]:
    """Strict metadata envelope for stock deep-dive JSON output."""
    return {
        "subject": ViewSubject(kind=subject_kind, id=subject_id.upper()).to_dict(),
        "verb": verb,
        "as_of": as_of.isoformat() if as_of else None,
        "window": window.to_dict() if window is not None else None,
        "source": source,
        "scope": scope,
        "scope_note": scope_note,
        "status": status.value,
        "fetch_hint": fetch_hint,
        "data": _json_safe(data),
    }


def default_ticker_fetch_hint(ticker: str) -> str:
    return f"saham fetch market {ticker.upper()}"


def missing_ticker_message(
    *,
    ticker: str,
    what: str,
    source: str | None = None,
    fetch_hint: str | None = None,
    for_date: date | str | None = None,
) -> str:
    """Human-readable empty-cache message for stock deep-dives."""
    lines = [f"No cached {what} for {ticker.upper()}."]
    if for_date is not None:
        lines.append(f"Date: {for_date}")
    if source:
        lines.append(f"Source: {source}")
    hint = fetch_hint or default_ticker_fetch_hint(ticker)
    lines.append(f"Run: {hint}")
    return "\n".join(lines)
