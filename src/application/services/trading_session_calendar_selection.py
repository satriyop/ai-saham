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
    - Two eligible snapshots with identical ``source_revision`` and coverage but
      different ordered sessions are a source conflict (raise).
    """
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

    # Source conflict: same revision + coverage, different session sets.
    by_rev_cov: dict[tuple[str, date, date], list[TradingSessionCalendarSnapshot]] = {}
    for snap in eligible:
        key = (snap.source_revision, snap.coverage_start, snap.coverage_end)
        by_rev_cov.setdefault(key, []).append(snap)
    for key, group in by_rev_cov.items():
        session_sets = {g.ordered_sessions for g in group}
        if len(session_sets) > 1:
            raise LearningContractError(
                "calendar source conflict: identical source_revision and coverage "
                f"with divergent sessions (revision={key[0]!r}, "
                f"coverage={key[1].isoformat()}..{key[2].isoformat()})"
            )

    return max(eligible, key=lambda s: (s.captured_at, s.snapshot_id))
