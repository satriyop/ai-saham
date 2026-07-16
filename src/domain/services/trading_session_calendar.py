"""
TradingSessionCalendar / KnownTradingSessionCalendar — DQ-002I.

A pure, IO-free abstraction over "how many actual IDX trading sessions
occurred in a given interval". This exists so session-aligned availability
decisions (see `AssessSourceAvailabilityUseCase`) never fall back to
calendar-day subtraction or weekday arithmetic — both of which produce
wrong lag counts across weekends and IDX holidays (e.g. Friday -> Monday is
1 trading session, not 3 calendar days).

`KnownTradingSessionCalendar` only knows what it was explicitly given. It
never assumes a weekday is a session, and it never assumes an interval
outside its proven `coverage_start..coverage_end` window contains zero
sessions — an unproven interval returns `None`, not 0. Building this from
real data (candle history) is an infrastructure concern; see
`src/infrastructure/persistence/ihsg_trading_session_calendar_provider.py`.

The existing weekday-only `trading_sessions_apart()` helper in
`src/domain/services/trading_calendar.py` is untouched and remains
available for explicitly-approximate display code; it must not be used for
authoritative availability decisions.

Layer: Domain (pure, no I/O, no external libraries)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


class TradingSessionCalendar(Protocol):
    """Answers "how many proven IDX sessions occurred in (earlier, later]"."""

    def sessions_apart(self, earlier: date, later: date) -> int | None:
        """Return the number of proven IDX sessions in (earlier, later].

        Return `None` when the calendar cannot prove complete coverage for
        the requested interval — callers must never treat `None` as `0`.
        """
        ...


@dataclass(frozen=True)
class KnownTradingSessionCalendar:
    """Immutable, bounded set of proven IDX trading sessions.

    `sessions` must be sorted ascending, unique, and each session date must
    fall within `[coverage_start, coverage_end]` — violations raise
    `ValueError` at construction time rather than silently normalizing,
    since a calendar that has to guess at its own session set cannot be
    trusted as "proven". A session date falling on a weekend is also
    rejected: a weekend can never legitimately be a proven IDX session, so
    one appearing in the input is a data/construction bug, not a valid
    (if unusual) trading day.
    """

    sessions: tuple[date, ...]
    coverage_start: date
    coverage_end: date

    def __post_init__(self) -> None:
        if self.coverage_start > self.coverage_end:
            raise ValueError(
                f"coverage_start ({self.coverage_start.isoformat()}) must not be after "
                f"coverage_end ({self.coverage_end.isoformat()})."
            )
        if len(set(self.sessions)) != len(self.sessions):
            raise ValueError("KnownTradingSessionCalendar sessions must not contain duplicates.")
        if list(self.sessions) != sorted(self.sessions):
            raise ValueError("KnownTradingSessionCalendar sessions must be sorted ascending.")
        for session in self.sessions:
            if session < self.coverage_start or session > self.coverage_end:
                raise ValueError(
                    f"session {session.isoformat()} is outside coverage "
                    f"[{self.coverage_start.isoformat()}, {self.coverage_end.isoformat()}]."
                )
            if session.weekday() >= 5:
                raise ValueError(
                    f"session {session.isoformat()} falls on a weekend; a proven IDX "
                    "session can never be a Saturday/Sunday."
                )

    def sessions_apart(self, earlier: date, later: date) -> int | None:
        if earlier > later:
            return None
        if earlier < self.coverage_start or later > self.coverage_end:
            return None
        # Both endpoints must themselves be proven sessions. A date inside
        # the coverage window that has no corresponding session is not
        # provably a trading day at all — it could be a genuine non-session
        # day or a source the caller never actually observed. Counting
        # sessions "between" an unproven endpoint would silently manufacture
        # authority (e.g. sessions_apart(unproven_monday, unproven_monday)
        # must not return 0/CURRENT).
        session_set = frozenset(self.sessions)
        if earlier not in session_set or later not in session_set:
            return None
        if earlier == later:
            return 0
        return sum(1 for session in self.sessions if earlier < session <= later)
