"""Gap-free availability calendar window selection (DQ-002I + historical capture).

`IHSGTradingSessionCalendarProvider` fail-closes when any Mon-Fri date in
`[coverage_start, coverage_end]` lacks an IHSG candle — it cannot tell IDX
holidays from data holes. A fixed 14-calendar-day lookback therefore often
includes holidays and disables source-availability assessment for entire
historical sessions (coverage stays 0 via AVAILABILITY_ASSESSOR_UNAVAILABLE).

This helper picks the widest suffix of proven IHSG sessions ending at
`coverage_end` whose inclusive weekday span is fully covered by those
sessions, capped at ``max_sessions``. Settlement assessment only needs a
few sessions of lookback (broker lag is 1); a gap-free short window is
enough to assess CURRENT/LATE without poisoning the calendar on holidays.

Layer: Application (pure policy helper — no I/O)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Sequence


def resolve_gap_free_availability_calendar_start(
    *,
    sessions: Sequence[date],
    coverage_end: date,
    max_sessions: int = 5,
) -> date:
    """Return coverage_start for a weekday-complete window ending at coverage_end.

    Prefers the longest eligible suffix (most sessions) so LATE-within-lag
    can still be measured when adjacent sessions have no intervening
    weekday holiday. Falls back to ``coverage_end`` (single-day window).
    """
    if max_sessions < 1:
        raise ValueError(f"max_sessions must be >= 1, got {max_sessions}")

    session_set = frozenset(day for day in sessions if day <= coverage_end)
    if coverage_end not in session_set:
        return coverage_end

    ordered = tuple(sorted(session_set))
    end_idx = ordered.index(coverage_end)
    earliest_idx = max(0, end_idx - max_sessions + 1)

    for start_idx in range(earliest_idx, end_idx + 1):
        start = ordered[start_idx]
        if _weekdays_fully_covered(start, coverage_end, session_set):
            return start
    return coverage_end


def _weekdays_fully_covered(
    start: date,
    end: date,
    session_set: frozenset[date],
) -> bool:
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in session_set:
            return False
        current += timedelta(days=1)
    return True
