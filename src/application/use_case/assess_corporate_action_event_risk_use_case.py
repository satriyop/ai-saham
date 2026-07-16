"""
AssessCorporateActionEventRiskUseCase — deterministic event-risk context for
a ticker as of a date, derived from the market-wide corporate action
calendar already synced locally.

Context only: this use case never touches SignalEngine, RiskEngine, or
AssessTradeSetupUseCase. It is consumed exclusively as optional diagnostics
in `saham analyze swing` (see ADR-032/ADR-033 verdict boundary).

Layer: Application
AI usage: None. Fully deterministic and config-driven.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from src.application.dto.corporate_action_policy import CorporateActionPolicyConfig
from src.application.ports.corporate_action_calendar_repository import (
    CorporateActionCalendarRepository,
)
from src.domain.value_objects.corporate_action_event_risk import (
    CorporateActionEventRiskSeverity,
    CorporateActionRiskAssessment,
    CorporateActionRiskEvent,
)


@dataclass(frozen=True)
class AssessCorporateActionEventRiskRequest:
    ticker: str
    as_of_date: date
    lookback_days_override: int | None = None
    lookahead_days_override: int | None = None
    as_of_fetched_at: str | None = None
    """DQ-002G point-in-time guard: ISO timestamp of the decision moment.

    When given, excludes calendar events/date-rows synced (`fetched_at`)
    after this timestamp — without it, a historical `as_of_date` can still
    see a corporate-action row that was not yet known/synced at that
    decision point, since `event_date` alone (which this event-risk window
    is built from) can legitimately be in the future. `None` (default)
    preserves prior unfiltered behavior for live callers, where
    `fetched_at` is naturally always <= "now" already.
    """


@dataclass(frozen=True)
class AssessCorporateActionEventRiskResponse:
    assessment: CorporateActionRiskAssessment


class AssessCorporateActionEventRiskUseCase:
    """Deterministic event-risk assessment over the market-wide calendar."""

    def __init__(
        self,
        repository: CorporateActionCalendarRepository,
        policy: CorporateActionPolicyConfig,
    ) -> None:
        self._repository = repository
        self._policy = policy

    def execute(
        self, request: AssessCorporateActionEventRiskRequest
    ) -> AssessCorporateActionEventRiskResponse:
        ticker = request.ticker.upper()
        as_of = request.as_of_date

        lookback = request.lookback_days_override
        if lookback is None:
            lookback = self._policy.max_lookback_days()
        lookahead = request.lookahead_days_override
        if lookahead is None:
            lookahead = self._policy.max_lookahead_days()

        query_from = as_of - timedelta(days=lookback)
        query_to = as_of + timedelta(days=lookahead)

        calendar_events = self._repository.get_events_for_ticker(
            ticker, query_from, query_to, as_of_fetched_at=request.as_of_fetched_at
        )

        matched: list[CorporateActionRiskEvent] = []
        for event in calendar_events:
            for date_row in event.dates:
                role_policy = self._policy.resolve(event.event_type.value, date_row.date_role.value)
                if role_policy is None:
                    continue
                days_from_as_of = (date_row.event_date - as_of).days
                if not (-role_policy.lookback_days <= days_from_as_of <= role_policy.lookahead_days):
                    continue
                matched.append(
                    CorporateActionRiskEvent(
                        event_type=event.event_type.value,
                        date_role=date_row.date_role.value,
                        event_date=date_row.event_date,
                        days_from_as_of=days_from_as_of,
                        severity=role_policy.severity,
                        flags=role_policy.flags,
                        note=event.event_note,
                        source_event_id=event.source_event_id,
                    )
                )

        matched.sort(
            key=lambda e: (
                abs(e.days_from_as_of),
                e.event_date,
                e.event_type,
                e.date_role,
                e.source_event_id,
            )
        )

        if not matched:
            assessment = CorporateActionRiskAssessment(
                ticker=ticker,
                as_of_date=as_of,
                severity=CorporateActionEventRiskSeverity.NONE,
                events=(),
                rationale=f"No configured event risk for {ticker} in the queried window.",
                nearest_event_date=None,
            )
            return AssessCorporateActionEventRiskResponse(assessment=assessment)

        overall_severity = max((e.severity for e in matched), key=lambda s: s.rank)
        assessment = CorporateActionRiskAssessment(
            ticker=ticker,
            as_of_date=as_of,
            severity=overall_severity,
            events=tuple(matched),
            rationale=_build_rationale(ticker, matched),
            nearest_event_date=matched[0].event_date,
        )
        return AssessCorporateActionEventRiskResponse(assessment=assessment)


def _build_rationale(ticker: str, matched: list[CorporateActionRiskEvent]) -> str:
    parts = [
        f"{e.event_type} {e.date_role} on {e.event_date.isoformat()} ({e.severity.value})"
        for e in matched
    ]
    return f"{ticker}: {'; '.join(parts)}"
