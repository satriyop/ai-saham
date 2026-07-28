"""
Policy rate step helpers — pure application functions (P2a).

Convert macro calendar events → PolicyRateStep and score net steps for
sector-macro policy_rate_steps factors.

Layer: Application
"""

from __future__ import annotations

from datetime import date

from src.domain.value_objects.macro_calendar_event import (
    MacroCalendarEvent,
)
from src.domain.value_objects.policy_rate_step import (
    PolicyRateDirection,
    PolicyRateStep,
    direction_from_actual_previous,
    step_sign,
)

# Virtual series key used in sector_macro factor_library (not a Yahoo ticker).
BI_RATE_SERIES_KEY = "BI_RATE"


def macro_events_to_policy_steps(
    events: list[MacroCalendarEvent] | tuple[MacroCalendarEvent, ...],
) -> tuple[PolicyRateStep, ...]:
    """Map bi_rate (or any) macro events to policy steps ordered by date ascending."""
    steps: list[PolicyRateStep] = []
    for ev in events:
        direction = direction_from_actual_previous(ev.actual, ev.previous)
        steps.append(
            PolicyRateStep(
                event_date=ev.event_date,
                title=ev.title,
                direction=direction,
                actual=ev.actual,
                previous=ev.previous,
                source_event_id=ev.source_event_id,
                source=ev.source,
            )
        )
    return tuple(sorted(steps, key=lambda s: (s.event_date, s.source_event_id)))


def filter_steps_on_or_before(
    steps: tuple[PolicyRateStep, ...] | list[PolicyRateStep],
    as_of: date,
) -> tuple[PolicyRateStep, ...]:
    return tuple(s for s in steps if s.event_date <= as_of)


def net_step_delta(
    steps: tuple[PolicyRateStep, ...] | list[PolicyRateStep],
) -> float | None:
    """Sum of hike(+1)/cut(-1) signs. None if no directional steps in the window."""
    signed = [step_sign(s.direction) for s in steps if s.direction != PolicyRateDirection.UNKNOWN]
    if not signed:
        # Holds-only still counts as known zero net if any HOLD present
        holds = [s for s in steps if s.direction is PolicyRateDirection.HOLD]
        if holds:
            return 0.0
        return None
    return float(sum(signed))
