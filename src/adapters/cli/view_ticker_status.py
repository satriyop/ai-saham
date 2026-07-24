"""
Freshness and empty-state helpers for the ticker dashboard.

Pure adapter helpers: no IO. Callers pass already-loaded cache facts.

Layer: Adapter
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


@dataclass(frozen=True)
class FreshnessItem:
    """One row in the dashboard freshness strip."""

    key: str
    label: str
    status: CacheStatus
    as_of: date | None = None
    age_days: int | None = None
    detail: str | None = None


# Default TTLs for "stale" classification when a fetched_at/as_of date exists.
DEFAULT_TTL_DAYS: dict[str, int] = {
    "price": 3,
    "flow": 2,
    "bandar": 2,
    "analyst": 7,
    "earnings": 14,
    "fundamentals": 14,
    "ownership": 14,
    "insider": 14,
    "corp": 14,
    "iev": 3,
    "sentiment": 14,
    "profile": 30,
}


def to_date(value: date | datetime | None) -> date | None:
    """Normalize date/datetime/None to a calendar date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def age_days(as_of: date | datetime | None, today: date) -> int | None:
    """Whole days between as_of and today, or None when unknown."""
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
    """Classify a single optional cached object (fundamentals, analyst, ...)."""
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
    """Classify a list-like cache (flow points, earnings, insider, ...)."""
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
    """Human-readable empty-panel body (without leading spaces)."""
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


def apply_staleness(
    status: CacheStatus,
    *,
    as_of: date | datetime | None,
    today: date,
    ttl_days: int,
) -> CacheStatus:
    """Upgrade OK → STALE when age exceeds TTL. Leaves missing/empty unchanged."""
    if status is not CacheStatus.OK:
        return status
    age = age_days(as_of, today)
    if age is not None and age > ttl_days:
        return CacheStatus.STALE
    return status


def build_freshness_item(
    key: str,
    label: str,
    status: CacheStatus,
    *,
    as_of: date | datetime | None = None,
    today: date | None = None,
    detail: str | None = None,
) -> FreshnessItem:
    """Construct a freshness row with normalized as_of/age."""
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
    return "✗"


def format_freshness_lines(
    ticker: str,
    items: list[FreshnessItem],
    *,
    as_of: date | None = None,
) -> list[str]:
    """Render compact multi-line freshness summary for the dashboard header."""
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

    lines = [header, marks]
    if missing:
        lines.append("Missing: " + ", ".join(missing))
    if empty:
        lines.append("Empty: " + ", ".join(empty))
    if stale:
        lines.append("Stale: " + ", ".join(stale))
    if not missing and not empty and not stale:
        lines.append("All key panels present")
    return lines


def default_fetch_hint(ticker: str) -> str:
    return f"saham fetch market {ticker.upper()}"
