"""
Corporate Action Event-Risk value objects.

Deterministic event-risk context derived from the market-wide corporate
action calendar (`corporate_action_calendar.py`) for a single ticker as of a
date. This is context/display evidence only — it is never consumed by
SignalEngine, RiskEngine, or `AssessTradeSetupUseCase`. The swing verdict
chain remains exclusively `SignalEngine + RiskEngine -> TradeSetup`
(ADR-026, ADR-032, ADR-033).

Layer: Domain
Depends on: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class CorporateActionEventRiskSeverity(Enum):
    NONE = "none"
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"

    @property
    def rank(self) -> int:
        """Ordering for deterministic max-severity aggregation."""
        return _SEVERITY_RANK[self]


_SEVERITY_RANK: dict[CorporateActionEventRiskSeverity, int] = {
    CorporateActionEventRiskSeverity.NONE: 0,
    CorporateActionEventRiskSeverity.INFO: 1,
    CorporateActionEventRiskSeverity.WARNING: 2,
    CorporateActionEventRiskSeverity.BLOCKING: 3,
}


class CorporateActionEventRiskFlag(Enum):
    PRICE_DISTORTION = "price_distortion"
    VOLUME_DISTORTION = "volume_distortion"
    LIQUIDITY_DISTORTION = "liquidity_distortion"
    SPECIAL_SITUATION = "special_situation"
    GOVERNANCE_CONTEXT = "governance_context"
    DISCLOSURE_CONTEXT = "disclosure_context"
    NEW_LISTING = "new_listing"


@dataclass(frozen=True)
class CorporateActionRiskEvent:
    """A single matched calendar event/date-role within the assessment window."""

    event_type: str
    date_role: str
    event_date: date
    days_from_as_of: int
    severity: CorporateActionEventRiskSeverity
    flags: tuple[CorporateActionEventRiskFlag, ...]
    note: str | None
    source_event_id: str


@dataclass(frozen=True)
class CorporateActionRiskAssessment:
    """
    Immutable deterministic event-risk context for a ticker as of a date.

    Produced by `AssessCorporateActionEventRiskUseCase` from the market-wide
    corporate action calendar. `events` is pre-sorted deterministically by
    the use case (abs(days_from_as_of), event_date, event_type, date_role,
    source_event_id). `severity` is the maximum severity across `events`, or
    NONE when no configured event risk is found in the query window.
    """

    ticker: str
    as_of_date: date
    severity: CorporateActionEventRiskSeverity
    events: tuple[CorporateActionRiskEvent, ...]
    rationale: str
    nearest_event_date: date | None

    @property
    def has_price_distortion_risk(self) -> bool:
        return self._has_flag(CorporateActionEventRiskFlag.PRICE_DISTORTION)

    @property
    def has_volume_distortion_risk(self) -> bool:
        return self._has_flag(CorporateActionEventRiskFlag.VOLUME_DISTORTION)

    @property
    def has_liquidity_distortion_risk(self) -> bool:
        return self._has_flag(CorporateActionEventRiskFlag.LIQUIDITY_DISTORTION)

    @property
    def has_special_situation_risk(self) -> bool:
        return self._has_flag(CorporateActionEventRiskFlag.SPECIAL_SITUATION)

    def _has_flag(self, flag: CorporateActionEventRiskFlag) -> bool:
        return any(flag in event.flags for event in self.events)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "as_of_date": self.as_of_date.isoformat(),
            "severity": self.severity.value,
            "rationale": self.rationale,
            "nearest_event_date": (
                self.nearest_event_date.isoformat() if self.nearest_event_date else None
            ),
            "events": [
                {
                    "event_type": e.event_type,
                    "date_role": e.date_role,
                    "event_date": e.event_date.isoformat(),
                    "days_from_as_of": e.days_from_as_of,
                    "severity": e.severity.value,
                    "flags": [f.value for f in e.flags],
                    "note": e.note,
                    "source_event_id": e.source_event_id,
                }
                for e in self.events
            ],
        }
