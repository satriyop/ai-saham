"""Tests for AssessSourceAvailabilityUseCase — DQ-002F per-source availability contract."""

from datetime import date, datetime

import pytest

from src.application.services.source_settlement_registry import (
    SettlementBasis,
    SourceSettlementRegistry,
    SourceSettlementRule,
    default_source_settlement_registry,
)
from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.source_availability import SourceAvailabilityStatus


def _session(
    latest_completed_session: date | None,
    decision_at: datetime,
) -> EffectiveMarketSession:
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=latest_completed_session,
        analysis_as_of=latest_completed_session,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="test_fixture",
        notes=(),
    )


def _wib(y, m, d, hh=16, mm=0) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IDX_TIMEZONE)


@pytest.fixture
def use_case() -> AssessSourceAvailabilityUseCase:
    return AssessSourceAvailabilityUseCase()


class TestSessionAlignedSources:
    def test_candles_current_when_observed_through_equals_decision_session(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="candles",
            effective_session=session,
            observed_through=date(2026, 7, 16),
        )

        assert result.status is SourceAvailabilityStatus.CURRENT
        assert result.is_authoritative is True

    def test_candles_stale_when_one_session_behind(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="candles",
            effective_session=session,
            observed_through=date(2026, 7, 15),
        )

        assert result.status is SourceAvailabilityStatus.STALE
        assert result.is_authoritative is False

    def test_candles_observed_after_session_is_invalid_never_current(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="candles",
            effective_session=session,
            observed_through=date(2026, 7, 17),
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False

    def test_broker_summaries_late_within_allowed_lag(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=date(2026, 7, 15),
        )

        assert result.status is SourceAvailabilityStatus.LATE
        assert result.is_authoritative is False

    def test_broker_summaries_stale_beyond_allowed_lag(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=date(2026, 7, 10),
        )

        assert result.status is SourceAvailabilityStatus.STALE
        assert result.is_authoritative is False

    def test_missing_source_is_unknown(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="broker_daily_flow",
            effective_session=session,
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN
        assert result.is_authoritative is False

    def test_unresolved_latest_completed_session_is_unknown(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(None, decision_at)

        result = use_case.execute(
            source_family="candles",
            effective_session=session,
            observed_through=date(2026, 7, 16),
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN

    def test_partial_flag_downgrades_current_to_partial(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="foreign_flow_points",
            effective_session=session,
            observed_through=date(2026, 7, 16),
            is_partial=True,
        )

        assert result.status is SourceAvailabilityStatus.PARTIAL
        assert result.is_authoritative is False


class TestFetchTimestampSources:
    def test_current_when_fetched_before_decision_at(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="analyst_cache",
            effective_session=session,
            available_at=_wib(2026, 7, 10),
        )

        assert result.status is SourceAvailabilityStatus.CURRENT
        assert result.is_authoritative is True

    def test_current_when_fetched_at_exactly_decision_at(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="company_fundamentals",
            effective_session=session,
            available_at=decision_at,
        )

        assert result.status is SourceAvailabilityStatus.CURRENT
        assert result.is_authoritative is True

    def test_fetched_after_decision_at_is_invalid_never_current(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="company_fundamentals",
            effective_session=session,
            available_at=_wib(2026, 7, 17),
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False

    def test_stale_beyond_max_staleness_days(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="seasonality_cache",
            effective_session=session,
            available_at=_wib(2026, 1, 1),
        )

        assert result.status is SourceAvailabilityStatus.STALE
        assert result.is_authoritative is False

    def test_missing_source_is_unknown(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="market_context_snapshots",
            effective_session=session,
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN
        assert result.is_authoritative is False


class TestDefaultRegistryCoverage:
    """Locks the exact set of Phase 2 authoritative source families so a
    missing family (e.g. foreign_flow_snapshots) fails a test instead of
    silently resolving to UNKNOWN/UNREGISTERED_SOURCE_FAMILY at call time."""

    def test_default_registry_covers_every_phase_2_source_family(self):
        registry = default_source_settlement_registry()

        assert set(registry.source_families()) == {
            "candles",
            "broker_summaries",
            "broker_daily_flow",
            "foreign_flow_points",
            "foreign_flow_snapshots",
            "analyst_cache",
            "company_fundamentals",
            "seasonality_cache",
            "corporate_action_events",
            "corporate_action_event_dates",
            "market_context_snapshots",
            "regime_observations",
            "sentiment",
        }


class TestUnregisteredSourceFamily:
    def test_unregistered_family_is_unknown_and_non_authoritative(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="not_a_real_source",
            effective_session=session,
            observed_through=date(2026, 7, 16),
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN
        assert result.is_authoritative is False


class TestSentimentIsDiagnosticOnlyGuard:
    """Sentiment must never become authoritative for Phase 2, under any input."""

    def test_sentiment_is_diagnostic_only_with_no_input(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(source_family="sentiment", effective_session=session)

        assert result.status is SourceAvailabilityStatus.DIAGNOSTIC_ONLY
        assert result.is_authoritative is False

    def test_sentiment_is_diagnostic_only_even_when_perfectly_current(self, use_case):
        """Adversarial case: feed sentiment the most favorable possible timing
        (observed exactly at decision_at) and prove it still cannot become
        authoritative."""
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="sentiment",
            effective_session=session,
            observed_through=date(2026, 7, 16),
            available_at=decision_at,
            is_partial=False,
        )

        assert result.status is SourceAvailabilityStatus.DIAGNOSTIC_ONLY
        assert result.is_authoritative is False

    def test_default_registry_sentiment_rule_is_not_authoritative_capable(self):
        registry = default_source_settlement_registry()
        rule = registry.rule_for("sentiment")

        assert rule is not None
        assert rule.settlement_basis is SettlementBasis.DIAGNOSTIC_ONLY
        assert rule.is_authoritative_capable is False

    def test_registry_construction_rejects_authoritative_diagnostic_rule(self):
        """A future edit that accidentally tries to make a diagnostic-only
        source authoritative must fail loudly at construction time, not
        silently pass through the use case."""
        with pytest.raises(ValueError):
            SourceSettlementRule(
                source_family="sentiment",
                settlement_basis=SettlementBasis.DIAGNOSTIC_ONLY,
                is_authoritative_capable=True,
            )

    def test_sentiment_cannot_be_swapped_in_as_authoritative_via_custom_registry(
        self, use_case
    ):
        """Even a custom registry cannot construct sentiment as authoritative —
        the guard is in the rule's own __post_init__, not the use case."""
        with pytest.raises(ValueError):
            SourceSettlementRegistry(
                {
                    "sentiment": SourceSettlementRule(
                        source_family="sentiment",
                        settlement_basis=SettlementBasis.DIAGNOSTIC_ONLY,
                        is_authoritative_capable=True,
                    )
                }
            )
