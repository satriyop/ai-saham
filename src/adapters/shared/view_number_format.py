"""Shared value formatting for multi-surface browse (CLI + TUI).

Layer: Adapter (shared pure presentation)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def format_value(value: Decimal) -> str:
    """Format large numbers for display (T/B/M/K)."""
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.2f}K"
    return f"{value:.2f}"


def format_signed(value: Decimal | float | int) -> str:
    """``format_value`` with an explicit leading ``+`` on positive values."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    s = format_value(d)
    if d > 0 and not s.startswith("+"):
        return f"+{s}"
    return s


def signed_with_tone(value: Decimal) -> tuple[str, str]:
    """Signed ``format_value`` plus a ``pos``/``neg``/``flat`` tone key."""
    base = format_value(value)
    if value > 0 and not base.startswith("+"):
        return f"+{base}", "pos"
    if value < 0:
        return base, "neg"
    return base, "flat"


def tone_for_signed(value: Decimal | float | int | None) -> str:
    """``pos``/``neg``/``neutral`` tone for an optional signed value."""
    if value is None:
        return "neutral"
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:
        return "neutral"
    if d > 0:
        return "pos"
    if d < 0:
        return "neg"
    return "neutral"


def format_price(value: Any) -> str:
    """Integer price with thousands separators; em dash when unavailable."""
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return str(value)


def format_date_short(raw: Any) -> str:
    """``YYYY-MM-DD`` from a date-like or string value; em dash when ``None``."""
    if raw is None:
        return "—"
    if hasattr(raw, "isoformat"):
        return str(raw.isoformat())[:10]
    return str(raw)[:10]
