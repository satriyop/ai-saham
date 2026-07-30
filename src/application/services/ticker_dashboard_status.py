"""
Freshness and empty-state classification for the ticker dashboard.

Pure application helpers: no IO.

Layer: Application
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class CacheStatus(str, Enum):
    """How to interpret a dashboard panel's local cache state."""

    OK = "ok"
    MISSING = "missing"
    EMPTY = "empty"
    STALE = "stale"
    ERROR = "error"


@dataclass(frozen=True)
class FreshnessItem:
    """One row in the dashboard freshness strip."""

    key: str
    label: str
    status: CacheStatus
    as_of: date | None = None
    age_days: int | None = None
    detail: str | None = None


DEFAULT_TTL_DAYS: dict[str, int] = {
    "price": 3,
    "flow": 2,
    "bandar": 2,
    "analyst": 7,
    "earnings": 14,
    "fundamentals": 14,
    # Long-term ownership (quarterly filings); refresh cadence is separate.
    "ownership": 90,
    "insider": 14,
    "corp": 14,
    "iev": 3,
    "sentiment": 14,
    "profile": 30,
}


def to_date(value: date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def age_days(as_of: date | datetime | None, today: date) -> int | None:
    d = to_date(as_of)
    if d is None:
        return None
    return (today - d).days


def classify_optional(
    value: object | None,
    *,
    as_of: date | datetime | None = None,
    today: date | None = None,
    ttl_days: int | None = None,
) -> CacheStatus:
    if value is None:
        return CacheStatus.MISSING
    if today is not None and ttl_days is not None:
        age = age_days(as_of, today)
        if age is not None and age > ttl_days:
            return CacheStatus.STALE
    return CacheStatus.OK


def classify_sequence(
    items: list | tuple | None,
    *,
    ever_fetched: bool = False,
    last_known: date | None = None,
    as_of: date | datetime | None = None,
    today: date | None = None,
    ttl_days: int | None = None,
) -> CacheStatus:
    if items:
        if today is not None and ttl_days is not None:
            age = age_days(as_of, today)
            if age is not None and age > ttl_days:
                return CacheStatus.STALE
        return CacheStatus.OK
    if ever_fetched or last_known is not None:
        return CacheStatus.EMPTY
    return CacheStatus.MISSING


def empty_state_message(
    status: CacheStatus,
    *,
    window_label: str | None = None,
    last_known: date | str | None = None,
    hint: str | None = None,
) -> str:
    if status is CacheStatus.MISSING:
        if hint:
            return f"not fetched — run: {hint}"
        return "not fetched"
    if status is CacheStatus.EMPTY:
        if window_label and last_known is not None:
            return f"none in {window_label} (last: {last_known})"
        if window_label:
            return f"none in {window_label}"
        return "none available"
    if status is CacheStatus.STALE:
        return "stale"
    return "not available"


def build_freshness_item(
    key: str,
    label: str,
    status: CacheStatus,
    *,
    as_of: date | datetime | None = None,
    today: date | None = None,
    detail: str | None = None,
) -> FreshnessItem:
    d = to_date(as_of)
    return FreshnessItem(
        key=key,
        label=label,
        status=status,
        as_of=d,
        age_days=age_days(d, today) if today is not None else None,
        detail=detail,
    )


def format_freshness_mark(status: CacheStatus) -> str:
    if status is CacheStatus.OK:
        return "✓"
    if status is CacheStatus.STALE:
        return "~"
    if status is CacheStatus.EMPTY:
        return "·"
    if status is CacheStatus.ERROR:
        return "!"
    return "✗"


def format_freshness_lines(
    ticker: str,
    items: list[FreshnessItem] | tuple[FreshnessItem, ...],
    *,
    as_of: date | None = None,
) -> list[str]:
    marks = "  ".join(f"{item.label} {format_freshness_mark(item.status)}" for item in items)
    header = f"{ticker.upper()}"
    if as_of is not None:
        header += f" · as of {as_of.isoformat()}"

    missing = [i.label for i in items if i.status is CacheStatus.MISSING]
    empty = [i.label for i in items if i.status is CacheStatus.EMPTY]
    stale = [
        f"{i.label} ({i.age_days}d)" if i.age_days is not None else i.label
        for i in items
        if i.status is CacheStatus.STALE
    ]
    errors = [i.label for i in items if i.status is CacheStatus.ERROR]

    lines = [header, marks]
    if missing:
        lines.append("Missing: " + ", ".join(missing))
    if empty:
        lines.append("Empty: " + ", ".join(empty))
    if stale:
        lines.append("Stale: " + ", ".join(stale))
    if errors:
        lines.append("Error: " + ", ".join(errors))
    if not missing and not empty and not stale and not errors:
        lines.append("All key panels present")
    return lines


def default_fetch_hint(ticker: str) -> str:
    return f"saham fetch market {ticker.upper()}"
