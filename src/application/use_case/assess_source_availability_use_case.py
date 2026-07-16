"""
AssessSourceAvailabilityUseCase — DQ-002F.

Deterministic per-source availability contract for Phase 2 authoritative
inputs. Given a decision timestamp (via an already-resolved
`EffectiveMarketSession`) and what is known about one source family's most
recent observation, decides whether that source was CURRENT, STALE, PARTIAL,
LATE, UNKNOWN, INVALID, or DIAGNOSTIC_ONLY at `decision_at` — and whether it
is allowed to be authoritative at all.

This use case does not read the database itself: callers already know (or
have already queried) `observed_through` / `available_at` for the source
they are asking about. It owns only the settlement *policy*, so the same
decision logic cannot drift between callers (screener, backtest, readiness,
CLI).

Does not change signal scoring, tuning, or persisted observations/labels.
Sentiment is hard-wired to DIAGNOSTIC_ONLY / is_authoritative=False via the
registry's own construction-time guard
(`SourceSettlementRule.__post_init__`) — this use case cannot make it
authoritative even if a caller supplies a perfectly current timestamp.

Layer: Application
AI usage: None
"""

from __future__ import annotations

from datetime import date, datetime

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.source_settlement_registry import (
    SettlementBasis,
    SourceSettlementRegistry,
    default_source_settlement_registry,
)
from src.domain.value_objects.source_availability import (
    SourceAvailabilityAssessment,
    SourceAvailabilityStatus,
)


class AssessSourceAvailabilityUseCase:
    """Assess one source family's availability at one decision timestamp."""

    def __init__(self, registry: SourceSettlementRegistry | None = None) -> None:
        self._registry = registry or default_source_settlement_registry()

    def execute(
        self,
        *,
        source_family: str,
        effective_session: EffectiveMarketSession,
        observed_through: date | None = None,
        available_at: datetime | None = None,
        is_partial: bool = False,
    ) -> SourceAvailabilityAssessment:
        decision_at = effective_session.decision_at
        rule = self._registry.rule_for(source_family)

        if rule is None:
            return self._assessment(
                source_family,
                decision_at,
                observed_through,
                available_at,
                SourceAvailabilityStatus.UNKNOWN,
                is_authoritative=False,
                reason="UNREGISTERED_SOURCE_FAMILY",
                notes=(
                    f"'{source_family}' has no settlement rule; it cannot be treated "
                    "as authoritative until a rule is added to the registry.",
                ),
            )

        if rule.settlement_basis is SettlementBasis.DIAGNOSTIC_ONLY:
            return self._assessment(
                source_family,
                decision_at,
                observed_through,
                available_at,
                SourceAvailabilityStatus.DIAGNOSTIC_ONLY,
                is_authoritative=False,
                reason="DIAGNOSTIC_ONLY_SOURCE",
                notes=(
                    f"'{source_family}' is diagnostic-only for Phase 2 and can never "
                    "be authoritative, regardless of timing.",
                ),
            )

        if observed_through is None and available_at is None:
            return self._assessment(
                source_family,
                decision_at,
                observed_through,
                available_at,
                SourceAvailabilityStatus.UNKNOWN,
                is_authoritative=False,
                reason="SOURCE_MISSING",
                notes=(f"No observation known for '{source_family}' at decision_at.",),
            )

        if available_at is not None and available_at > decision_at:
            return self._assessment(
                source_family,
                decision_at,
                observed_through,
                available_at,
                SourceAvailabilityStatus.INVALID,
                is_authoritative=False,
                reason="FUTURE_OBSERVATION_LEAKAGE",
                notes=(
                    f"'{source_family}' was observed at {available_at.isoformat()}, "
                    f"after decision_at ({decision_at.isoformat()}); this row cannot "
                    "be knowable at decision time.",
                ),
            )

        if rule.settlement_basis is SettlementBasis.SESSION_ALIGNED:
            status, reason, notes = self._assess_session_aligned(
                rule.settlement_lag_days, effective_session, observed_through
            )
        else:
            status, reason, notes = self._assess_fetch_timestamp(
                rule.max_staleness_days, decision_at, available_at
            )

        if is_partial and status in (
            SourceAvailabilityStatus.CURRENT,
            SourceAvailabilityStatus.LATE,
        ):
            status = SourceAvailabilityStatus.PARTIAL
            reason = "PARTIAL_COVERAGE"
            notes = notes + ("Source is timely but reports incomplete coverage.",)

        is_authoritative = (
            rule.is_authoritative_capable and status is SourceAvailabilityStatus.CURRENT
        )

        return self._assessment(
            source_family,
            decision_at,
            observed_through,
            available_at,
            status,
            is_authoritative=is_authoritative,
            reason=reason,
            notes=notes,
        )

    @staticmethod
    def _assess_session_aligned(
        settlement_lag_days: int,
        effective_session: EffectiveMarketSession,
        observed_through: date | None,
    ) -> tuple[SourceAvailabilityStatus, str, tuple[str, ...]]:
        latest_completed_session = effective_session.latest_completed_session

        if latest_completed_session is None:
            return (
                SourceAvailabilityStatus.UNKNOWN,
                "LATEST_COMPLETED_SESSION_UNRESOLVED",
                ("The effective market session could not resolve a completed session.",),
            )

        if observed_through is None:
            return (
                SourceAvailabilityStatus.UNKNOWN,
                "SOURCE_MISSING",
                ("No session-aligned observation known for this source.",),
            )

        gap_days = (latest_completed_session - observed_through).days

        if gap_days < 0:
            return (
                SourceAvailabilityStatus.INVALID,
                "SESSION_LEAKAGE_FUTURE_OBSERVATION",
                (
                    f"observed_through ({observed_through.isoformat()}) is after the "
                    f"latest completed session ({latest_completed_session.isoformat()}).",
                ),
            )

        if gap_days == 0:
            return (SourceAvailabilityStatus.CURRENT, "SESSION_ALIGNED_CURRENT", ())

        if gap_days <= settlement_lag_days:
            return (
                SourceAvailabilityStatus.LATE,
                "SESSION_ALIGNED_LATE_WITHIN_LAG",
                (
                    f"observed_through is {gap_days} session(s) behind the latest "
                    f"completed session ({latest_completed_session.isoformat()}), "
                    f"within the expected {settlement_lag_days}-session settlement lag.",
                ),
            )

        return (
            SourceAvailabilityStatus.STALE,
            "SESSION_ALIGNED_STALE",
            (
                f"observed_through is {gap_days} session(s) behind the latest "
                f"completed session ({latest_completed_session.isoformat()}), beyond "
                f"the expected {settlement_lag_days}-session settlement lag.",
            ),
        )

    @staticmethod
    def _assess_fetch_timestamp(
        max_staleness_days: int | None,
        decision_at: datetime,
        available_at: datetime | None,
    ) -> tuple[SourceAvailabilityStatus, str, tuple[str, ...]]:
        if available_at is None:
            return (
                SourceAvailabilityStatus.UNKNOWN,
                "SOURCE_MISSING",
                ("No fetch/observation timestamp known for this source.",),
            )

        age_days = (decision_at.date() - available_at.date()).days

        if max_staleness_days is not None and age_days > max_staleness_days:
            return (
                SourceAvailabilityStatus.STALE,
                "FETCH_TIMESTAMP_STALE",
                (
                    f"available_at is {age_days} day(s) old, beyond the "
                    f"{max_staleness_days}-day freshness window.",
                ),
            )

        return (SourceAvailabilityStatus.CURRENT, "FETCH_TIMESTAMP_CURRENT", ())

    @staticmethod
    def _assessment(
        source_family: str,
        decision_at: datetime,
        observed_through: date | None,
        available_at: datetime | None,
        status: SourceAvailabilityStatus,
        *,
        is_authoritative: bool,
        reason: str,
        notes: tuple[str, ...],
    ) -> SourceAvailabilityAssessment:
        return SourceAvailabilityAssessment(
            source_family=source_family,
            decision_at=decision_at,
            observed_through=observed_through,
            available_at=available_at,
            status=status,
            is_authoritative=is_authoritative,
            reason=reason,
            notes=notes,
        )
