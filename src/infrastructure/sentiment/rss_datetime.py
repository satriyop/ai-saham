"""Parse RFC-822 RSS dates without depending on the host timezone database.

``datetime.strptime(..., "%Z")`` only accepts zone names the local C library
knows. Ubuntu CI with ``TZ=UTC`` does not know ``WIB``/``WITA``/``WIT``, so
IDX RSS timestamps parse as None there while they pass on a Jakarta laptop.

Layer: Infrastructure
"""

from __future__ import annotations

from datetime import datetime

_IDX_ZONE_OFFSETS = {
    "WIB": "+0700",
    "WITA": "+0800",
    "WIT": "+0900",
}

_FORMATS = (
    "%a, %d %b %Y %H:%M:%S %z",
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S",
)


def parse_rss_datetime(date_str: str) -> datetime | None:
    """Return a naive datetime, or None when the string is not RFC-822-like."""
    raw = (date_str or "").strip()
    if not raw:
        return None
    normalized = raw
    for name, offset in _IDX_ZONE_OFFSETS.items():
        token = f" {name}"
        if raw.endswith(token):
            normalized = raw[: -len(name)] + offset
            break
    for fmt in _FORMATS:
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None
