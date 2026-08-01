"""
Trading calendar utilities — pure date arithmetic, no external dependencies.

No holiday calendar is maintained. Only weekends (Saturday/Sunday) are excluded.
Public holidays may produce a false +1 session count, which is acceptable — the
direction of the lag is always correct.

Layer: Domain (pure, no I/O, no external libraries)
"""

from __future__ import annotations

from datetime import date, timedelta


def is_weekday_session(d: date) -> bool:
    """Return True when ``d`` falls on Mon–Fri (approximate IDX session day)."""
    return d.weekday() < 5  # 0=Mon … 4=Fri


def trading_sessions_apart(earlier: date, later: date) -> int:
    """Count weekday (Mon–Fri) trading sessions strictly between two dates.

    Returns 0 when the dates are equal or differ only by weekend days (e.g.
    Friday → Monday). Returns a positive integer for any genuine session gap.
    The sign convention is always non-negative; caller is responsible for
    determining which date is earlier.

    Args:
        earlier: The older date.
        later:   The newer date.

    Returns:
        Number of Mon–Fri days in the half-open interval (earlier, later].
        Returns 0 if earlier >= later.
    """
    if earlier >= later:
        return 0
    sessions = 0
    current = earlier
    while current < later:
        current += timedelta(days=1)
        if is_weekday_session(current):
            sessions += 1
    return sessions


def inclusive_weekday_sessions(start: date, end: date) -> int | None:
    """Count Mon–Fri sessions in the closed interval ``[start, end]``.

    Both endpoints must themselves be weekday session dates. Returns ``None``
    when the interval is inverted or either endpoint falls on a weekend —
    callers must not treat an unproven endpoint as a market session.

    This is the pure weekday-session authority used by readiness for exact
    H3/H10/H20 path-label windows (no holiday calendar; no I/O).
    """
    if start > end:
        return None
    if not is_weekday_session(start) or not is_weekday_session(end):
        return None
    return 1 + trading_sessions_apart(start, end)


def first_weekday_session_after(d: date) -> date:
    """Return the first Mon–Fri date strictly after ``d``."""
    current = d + timedelta(days=1)
    while not is_weekday_session(current):
        current += timedelta(days=1)
    return current


def nth_weekday_session_on_or_after(start: date, n: int) -> date:
    """Return the ``n``-th Mon–Fri session on or after ``start`` (1-indexed).

    ``n`` must be >= 1. Used by fixtures and pure arithmetic that need exact
    N-session endpoints without market-data I/O.
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    current = start
    seen = 0
    while True:
        if is_weekday_session(current):
            seen += 1
            if seen == n:
                return current
        current += timedelta(days=1)


def is_same_trading_session(d1: date, d2: date) -> bool:
    """Return True when two dates have zero trading sessions between them.

    Treats Friday and the following Monday as the same effective session
    (no trading on Saturday/Sunday).
    """
    a, b = (d1, d2) if d1 <= d2 else (d2, d1)
    return trading_sessions_apart(a, b) == 0
