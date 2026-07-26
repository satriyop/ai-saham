"""IDX opening-session capture phase classification.

Moved from OpeningSnapshotUseCase (retired: research pre-open capture is the
only decision writer).

Layer: Application
"""

from __future__ import annotations

from datetime import datetime

from src.domain.value_objects.idx_market import (
    IDX_TIMEZONE,
    NCP_LOCK_TIME,
    OPEN_SESSION_END,
    PRE_OPEN_MATCHING_START,
)
from src.domain.value_objects.idx_market import (
    PRE_OPEN_START as PRE_NCP_START,
)
from src.domain.value_objects.idx_market import (
    REGULAR_OPEN as REGULAR_OPEN_TIME,
)


def classify_opening_capture_phase(
    captured_at: datetime,
    *,
    is_trading_day: bool = True,
) -> str:
    """Classify a capture timestamp into deterministic IDX opening phases."""
    if not is_trading_day:
        return "NON_TRADING_DAY"
    local = captured_at.astimezone(IDX_TIMEZONE)
    current = local.time()
    if PRE_NCP_START <= current < NCP_LOCK_TIME:
        return "PRE_NCP"
    if NCP_LOCK_TIME <= current < PRE_OPEN_MATCHING_START:
        return "NCP_LOCKED"
    if PRE_OPEN_MATCHING_START <= current < REGULAR_OPEN_TIME:
        return "PRE_OPEN_MATCHING"
    if REGULAR_OPEN_TIME <= current <= OPEN_SESSION_END:
        return "OPEN"
    if current > OPEN_SESSION_END:
        return "POST_OPEN"
    return "OUT_OF_SESSION"


def capture_confidence_for_phase(phase: str) -> str:
    if phase == "NCP_LOCKED":
        return "HIGH"
    if phase == "PRE_NCP":
        return "MEDIUM"
    return "LOW"
