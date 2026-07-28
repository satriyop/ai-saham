"""
PolicyRateStep — one central-bank / policy-rate decision event (ADR-055 / P2a).

Derived from macro calendar (category bi_rate). Not a continuous yield series.
Used as DIAGNOSTIC input to sector-macro rates maps (bank pilot).

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any


class PolicyRateDirection(str, Enum):
    HIKE = "hike"
    CUT = "cut"
    HOLD = "hold"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PolicyRateStep:
    """A single policy-rate decision step (e.g. BI rate announcement)."""

    event_date: date
    title: str
    direction: PolicyRateDirection
    actual: str | None = None
    previous: str | None = None
    source_event_id: str = ""
    source: str = "stockbit"

    def __post_init__(self) -> None:
        title = (self.title or "").strip()
        if not title:
            raise ValueError("title is required")
        object.__setattr__(self, "title", title)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_date": self.event_date.isoformat(),
            "title": self.title,
            "direction": self.direction.value,
            "actual": self.actual,
            "previous": self.previous,
            "source_event_id": self.source_event_id,
            "source": self.source,
        }


def parse_rate_number(raw: str | None) -> float | None:
    """Parse Stockbit-style rate strings (``5.50%``, ``5,50``) to float percent points."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def direction_from_actual_previous(actual: str | None, previous: str | None) -> PolicyRateDirection:
    """Compare actual vs previous levels. Equal → HOLD; unparseable → UNKNOWN."""
    a = parse_rate_number(actual)
    p = parse_rate_number(previous)
    if a is None or p is None:
        return PolicyRateDirection.UNKNOWN
    if a > p:
        return PolicyRateDirection.HIKE
    if a < p:
        return PolicyRateDirection.CUT
    return PolicyRateDirection.HOLD


def step_sign(direction: PolicyRateDirection) -> int:
    """HIKE +1, CUT -1, HOLD/UNKNOWN 0 (for net step aggregation)."""
    if direction is PolicyRateDirection.HIKE:
        return 1
    if direction is PolicyRateDirection.CUT:
        return -1
    return 0
