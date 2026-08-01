"""Deterministic calendar snapshot selection."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.application.services.trading_session_calendar_selection import (
    select_calendar_snapshot,
)
from src.domain.value_objects.learning_artifacts import LearningContractError
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
)

SESSIONS = tuple(
    d
    for d in (
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
        date(2026, 7, 6),
        date(2026, 7, 7),
        date(2026, 7, 8),
        date(2026, 7, 9),
        date(2026, 7, 10),
        date(2026, 7, 13),
        date(2026, 7, 14),
        date(2026, 7, 15),
        date(2026, 7, 16),
    )
)


def _snap(
    *,
    captured_at: datetime,
    revision: str = "rev-a",
    sessions: tuple[date, ...] = SESSIONS,
    start: date = date(2026, 7, 1),
    end: date = date(2026, 7, 31),
) -> TradingSessionCalendarSnapshot:
    return TradingSessionCalendarSnapshot.create(
        coverage_start=start,
        coverage_end=end,
        ordered_sessions=sessions,
        source_revision=revision,
        captured_at=captured_at,
    )


def test_newest_captured_at_wins_independent_of_list_order() -> None:
    older = _snap(captured_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    newer = _snap(captured_at=datetime(2026, 7, 15, tzinfo=timezone.utc), revision="rev-b")
    for order in ((older, newer), (newer, older)):
        picked = select_calendar_snapshot(order, signal_date=date(2026, 7, 1), horizon_days=3)
        assert picked is not None
        assert picked.snapshot_id == newer.snapshot_id


def test_snapshot_id_tiebreak_when_captured_at_equal() -> None:
    t = datetime(2026, 7, 10, tzinfo=timezone.utc)
    a = _snap(captured_at=t, revision="rev-x")
    b = _snap(captured_at=t, revision="rev-y")
    # Different revisions → different snapshot_ids
    picked = select_calendar_snapshot((a, b), signal_date=date(2026, 7, 1), horizon_days=3)
    assert picked is not None
    assert picked.snapshot_id == max(a.snapshot_id, b.snapshot_id)


def test_source_conflict_same_revision_coverage_divergent_sessions() -> None:
    t = datetime(2026, 7, 10, tzinfo=timezone.utc)
    s1 = SESSIONS
    s2 = SESSIONS[:-1] + (date(2026, 7, 17),)
    a = _snap(captured_at=t, revision="same", sessions=s1)
    b = _snap(captured_at=t, revision="same", sessions=s2)
    with pytest.raises(LearningContractError, match="source conflict"):
        select_calendar_snapshot((a, b), signal_date=date(2026, 7, 1), horizon_days=3)


def test_ineligible_yahoo_snapshot_ignored() -> None:
    yahoo = TradingSessionCalendarSnapshot.create(
        coverage_start=date(2026, 7, 1),
        coverage_end=date(2026, 7, 31),
        ordered_sessions=SESSIONS,
        source_revision="rev",
        captured_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
        source="yahoo",
    )
    good = _snap(captured_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    picked = select_calendar_snapshot((yahoo, good), signal_date=date(2026, 7, 1), horizon_days=3)
    assert picked is not None
    assert picked.snapshot_id == good.snapshot_id
