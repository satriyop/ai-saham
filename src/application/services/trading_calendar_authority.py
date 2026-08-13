"""
CalendarAuthority — what the attested trading calendar can and cannot confirm.

Trading session calendar snapshots are rolling ~30-day windows, so no single
snapshot spans a mature corpus. Any consumer that reads only the newest snapshot
silently blinds itself to older dates, and any consumer that unions sessions
without also unioning *coverage* loses the ability to tell a confirmed market
holiday apart from a date nothing ever attested.

Both mistakes are easy and neither fails loudly, which is why this lives in one
place instead of being re-derived per caller.

Two questions, deliberately kept separate:

* ``covers(day)`` — does any snapshot claim authority over this date?
* ``is_session(day)`` — did the market actually open on it?

A caller that collapses the two ends up reporting a guess as a fact. Absence of
coverage is not evidence of a holiday.

Layer: Application
Depends on: Domain value objects (trading session calendar snapshot)
AI usage: None
"""

from __future__ import annotations

from datetime import date

from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)


class CalendarAuthority:
    """Union of every attested calendar snapshot's sessions and coverage."""

    def __init__(self, snapshots: tuple[TradingSessionCalendarSnapshot, ...]) -> None:
        self._sessions: frozenset[date] = frozenset(
            session for snapshot in snapshots for session in snapshot.ordered_sessions
        )
        self._coverage: tuple[tuple[date, date], ...] = tuple(
            (snapshot.coverage_start, snapshot.coverage_end) for snapshot in snapshots
        )
        self.snapshot_ids: tuple[str, ...] = tuple(
            sorted(snapshot.snapshot_id for snapshot in snapshots)
        )

    def covers(self, day: date) -> bool:
        return any(start <= day <= end for start, end in self._coverage)

    def is_session(self, day: date) -> bool:
        return day in self._sessions
