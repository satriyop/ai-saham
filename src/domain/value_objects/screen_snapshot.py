"""
ScreenSnapshotEntry — one ticker's position in a saved screener run.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ScreenSnapshotEntry:
    """Immutable record of one ticker inside a named screener snapshot."""

    name: str  # user-defined snapshot label (e.g. "morning-watch")
    saved_at: datetime  # when the snapshot was saved
    universe: str  # universe screened (e.g. "lq45", "cached")
    window_days: int  # broker-session window used

    ticker: str
    rank: int  # 1-based position in the screener results
    accum_score: float  # composite foreign-flow score (0-100)
    signal_score: float | None  # SignalAssessment.assessment.score (0–100); None if not available
    consecutive_streak: int
    net_buy_ratio: float
    bci_label: str | None
