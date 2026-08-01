"""Pure selection of an eligible trading-session calendar snapshot.

Layer: Application (pure)
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

from src.domain.value_objects.learning_artifacts import LearningContractError
from src.domain.value_objects.trading_session_calendar_snapshot import (
    TradingSessionCalendarSnapshot,
    validate_active_stockbit_calendar_snapshot,
)


def assert_no_calendar_source_conflicts(
    snapshots: Sequence[TradingSessionCalendarSnapshot],
) -> None:
    """Fail closed if any active snapshots share authority key with different sessions.

    Authority key: contract_id, source, benchmark, coverage_start/end, source_revision.
    """
    by_key: dict[tuple[str, str, str, date, date, str], list[TradingSessionCalendarSnapshot]] = {}
    for snapshot in snapshots:
        try:
            validate_active_stockbit_calendar_snapshot(snapshot)
        except LearningContractError:
            continue
        key = (
            snapshot.contract_id,
            snapshot.source,
            snapshot.benchmark,
            snapshot.coverage_start,
            snapshot.coverage_end,
            snapshot.source_revision,
        )
        by_key.setdefault(key, []).append(snapshot)
    for key, group in by_key.items():
        session_sets = {g.ordered_sessions for g in group}
        if len(session_sets) > 1:
            raise LearningContractError(
                "calendar source conflict: identical contract/source/benchmark/"
                "coverage/source_revision with divergent sessions "
                f"(revision={key[5]!r}, "
                f"coverage={key[3].isoformat()}..{key[4].isoformat()})"
            )


def select_calendar_snapshot(
    snapshots: Sequence[TradingSessionCalendarSnapshot],
    *,
    signal_date: date,
    horizon_days: int,
) -> TradingSessionCalendarSnapshot | None:
    """Pick the newest eligible active Stockbit/IHSG snapshot for first-N proof.

    Policy (locked):
    - Snapshot must pass active Stockbit/IHSG validation.
    - Must prove first ``horizon_days`` sessions after ``signal_date``.
    - Newest ``captured_at`` wins; ``snapshot_id`` is the deterministic tie-breaker.
    - Two eligible snapshots with identical authority key but different ordered
      sessions are a source conflict (raise) — never treated as ordinary skip.
    """
    assert_no_calendar_source_conflicts(snapshots)
    eligible: list[TradingSessionCalendarSnapshot] = []
    for snapshot in snapshots:
        try:
            validate_active_stockbit_calendar_snapshot(snapshot)
        except LearningContractError:
            continue
        if snapshot.first_n_sessions_after(signal_date, horizon_days) is not None:
            eligible.append(snapshot)
    if not eligible:
        return None
    return max(eligible, key=lambda s: (s.captured_at, s.snapshot_id))
