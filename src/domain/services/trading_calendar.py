"""
Trading calendar utilities — pure date arithmetic, no external dependencies.

No holiday calendar is maintained. Only weekends (Saturday/Sunday) are excluded.
Public holidays may produce a false +1 session count, which is acceptable — the
direction of the lag is always correct.

Layer: Domain (pure, no I/O, no external libraries)
"""

from __future__ import annotations

from datetime import date, timedelta


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
        if current.weekday() < 5:  # 0=Mon … 4=Fri
            sessions += 1
    return sessions


def is_same_trading_session(d1: date, d2: date) -> bool:
    """Return True when two dates have zero trading sessions between them.

    Treats Friday and the following Monday as the same effective session
    (no trading on Saturday/Sunday).
    """
    a, b = (d1, d2) if d1 <= d2 else (d2, d1)
    return trading_sessions_apart(a, b) == 0
