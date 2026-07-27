"""Tests for AssessSourceAvailabilityUseCase — DQ-002F/DQ-002I per-source availability contract."""

from datetime import date, datetime, timedelta

import pytest

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.source_settlement_registry import (
    SettlementBasis,
    SourceSettlementRegistry,
    SourceSettlementRule,
    default_source_settlement_registry,
)
from src.application.use_case.assess_source_availability_use_case import (
    AssessSourceAvailabilityUseCase,
)
from src.domain.services.trading_session_calendar import KnownTradingSessionCalendar
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


def _all_weekdays(start: date, end: date) -> tuple[date, ...]:
    """Every Mon-Fri date in [start, end] — a test-only fixture calendar,
    not production weekday-fallback logic. None of the dates this file's
    pre-existing tests use (2026-07-10..2026-07-17) cross an IDX holiday,
    so this preserves their exact previous gap counts under real
    trading-session-distance calculation."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return tuple(days)


def _default_calendar() -> KnownTradingSessionCalendar:
    start = date(2026, 1, 1)
    end = date(2026, 12, 31)
    return KnownTradingSessionCalendar(
        sessions=_all_weekdays(start, end), coverage_start=start, coverage_end=end
    )


@pytest.fixture
def use_case() -> AssessSourceAvailabilityUseCase:
    return AssessSourceAvailabilityUseCase(calendar=_default_calendar())


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


class TestTradingSessionDistance:
    """DQ-002I: session-aligned lag must use proven IDX trading-session
    distance (via the injected calendar), never calendar-day subtraction
    or weekday arithmetic."""

    FRIDAY = date(2026, 7, 17)
    MONDAY = date(2026, 7, 20)
    TUESDAY = date(2026, 7, 21)

    def test_friday_to_monday_is_one_session_behind_and_late_not_stale(self):
        """Old bug: (Monday - Friday).days == 3, which would have been
        STALE for a lag=1 broker source. Correct: 1 trading session."""
        calendar = KnownTradingSessionCalendar(
            sessions=(self.FRIDAY, self.MONDAY),
            coverage_start=self.FRIDAY,
            coverage_end=self.MONDAY,
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
        session = _session(self.MONDAY, _wib(2026, 7, 20))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.FRIDAY,
        )

        assert result.status is SourceAvailabilityStatus.LATE
        assert result.is_authoritative is False
        assert any("1 trading session" in note for note in result.notes)

    def test_friday_to_tuesday_is_two_sessions_behind_and_stale(self):
        calendar = KnownTradingSessionCalendar(
            sessions=(self.FRIDAY, self.MONDAY, self.TUESDAY),
            coverage_start=self.FRIDAY,
            coverage_end=self.TUESDAY,
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
        session = _session(self.TUESDAY, _wib(2026, 7, 21))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.FRIDAY,
        )

        assert result.status is SourceAvailabilityStatus.STALE
        assert result.is_authoritative is False
        assert any("2 trading session" in note for note in result.notes)

    def test_multi_calendar_day_holiday_gap_with_one_real_session_is_late_not_stale(self):
        """Friday -> Tuesday spans 4 calendar days, but Monday is an IDX
        holiday (deliberately absent from the session set) — only Tuesday
        is a real elapsed session, so this is 1 session behind, not 2 and
        not the old (wrong) 4-calendar-day count."""
        calendar = KnownTradingSessionCalendar(
            sessions=(self.FRIDAY, self.TUESDAY),  # Monday deliberately absent
            coverage_start=self.FRIDAY,
            coverage_end=self.TUESDAY,
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
        session = _session(self.TUESDAY, _wib(2026, 7, 21))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.FRIDAY,
        )

        assert result.status is SourceAvailabilityStatus.LATE
        assert result.is_authoritative is False

    def test_candles_friday_to_monday_one_session_behind_is_still_stale(self):
        """Candles have zero allowed lag: even a correct 1-trading-session
        gap (not the old buggy 3-calendar-day count) is STALE, because
        candles must be exactly current."""
        calendar = KnownTradingSessionCalendar(
            sessions=(self.FRIDAY, self.MONDAY),
            coverage_start=self.FRIDAY,
            coverage_end=self.MONDAY,
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
        session = _session(self.MONDAY, _wib(2026, 7, 20))

        result = use_case.execute(
            source_family="candles",
            effective_session=session,
            observed_through=self.FRIDAY,
        )

        assert result.status is SourceAvailabilityStatus.STALE
        assert result.is_authoritative is False

    def test_future_observed_through_remains_invalid_regardless_of_calendar(self):
        calendar = KnownTradingSessionCalendar(
            sessions=(self.FRIDAY, self.MONDAY),
            coverage_start=self.FRIDAY,
            coverage_end=self.MONDAY,
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
        session = _session(self.FRIDAY, _wib(2026, 7, 17))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.MONDAY,  # after latest_completed_session
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False

    def test_missing_calendar_coverage_is_unknown_not_zero_sessions(self):
        """The calendar cannot prove coverage for this interval (it only
        knows about a different date range entirely) — this must resolve
        to UNKNOWN, never silently to CURRENT (0 sessions) or any other
        status that would grant authority."""
        unrelated_calendar = KnownTradingSessionCalendar(
            sessions=(date(2026, 1, 5), date(2026, 1, 6)),
            coverage_start=date(2026, 1, 1),
            coverage_end=date(2026, 1, 31),
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=unrelated_calendar)
        session = _session(self.MONDAY, _wib(2026, 7, 20))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.FRIDAY,
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN
        assert result.is_authoritative is False
        assert result.reason == "TRADING_CALENDAR_COVERAGE_UNPROVEN"

    def test_missing_calendar_coverage_produces_no_expected_available_at(self):
        unrelated_calendar = KnownTradingSessionCalendar(
            sessions=(), coverage_start=date(2026, 1, 1), coverage_end=date(2026, 1, 31)
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=unrelated_calendar)
        session = _session(self.MONDAY, _wib(2026, 7, 20))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.FRIDAY,
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN
        assert result.expected_available_at is None

    def test_non_session_latest_completed_session_endpoint_is_unknown(self):
        """`latest_completed_session` (MONDAY) is inside coverage but was
        never proven as a session (only Friday/Tuesday are) — this must
        resolve to UNKNOWN/non-authoritative, never CURRENT/LATE/STALE."""
        calendar = KnownTradingSessionCalendar(
            sessions=(self.FRIDAY, self.TUESDAY),
            coverage_start=self.FRIDAY,
            coverage_end=self.TUESDAY,
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
        session = _session(self.MONDAY, _wib(2026, 7, 20))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.FRIDAY,
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN
        assert result.is_authoritative is False
        assert result.reason == "TRADING_CALENDAR_COVERAGE_UNPROVEN"

    def test_non_session_observed_through_endpoint_is_unknown(self):
        """`observed_through` (MONDAY) is inside coverage but was never
        proven as a session — must resolve to UNKNOWN, never silently
        treated as 0/1 sessions apart."""
        calendar = KnownTradingSessionCalendar(
            sessions=(self.FRIDAY, self.TUESDAY),
            coverage_start=self.FRIDAY,
            coverage_end=self.TUESDAY,
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
        session = _session(self.TUESDAY, _wib(2026, 7, 21))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.MONDAY,
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN
        assert result.is_authoritative is False
        assert result.reason == "TRADING_CALENDAR_COVERAGE_UNPROVEN"

    def test_non_session_same_date_endpoint_is_unknown_not_current(self):
        """observed_through == latest_completed_session == MONDAY, but
        MONDAY was never proven as a session — must not silently resolve
        to CURRENT/is_authoritative=True."""
        calendar = KnownTradingSessionCalendar(
            sessions=(self.FRIDAY, self.TUESDAY),
            coverage_start=self.FRIDAY,
            coverage_end=self.TUESDAY,
        )
        use_case = AssessSourceAvailabilityUseCase(calendar=calendar)
        session = _session(self.MONDAY, _wib(2026, 7, 20))

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=self.MONDAY,
        )

        assert result.status is SourceAvailabilityStatus.UNKNOWN
        assert result.is_authoritative is False
        assert result.reason == "TRADING_CALENDAR_COVERAGE_UNPROVEN"


class TestProviderSettlementCutoff:
    """DQ-002H: provider settlement cutoff metadata/notes for SESSION_ALIGNED
    broker/flow sources. Chosen behavior (documented in
    AssessSourceAvailabilityUseCase._assess_session_aligned): LATE means
    "within allowed settlement lag, even after cutoff" — the cutoff only
    adds explanatory notes/`expected_available_at`, it never changes
    LATE-vs-STALE, which remains governed solely by settlement_lag_days.
    This preserves DQ-002F/G runtime behavior exactly; no status/reason
    codes changed for any existing case."""

    def test_broker_source_one_session_behind_before_cutoff_is_late_with_cutoff_metadata(
        self, use_case
    ):
        decision_at = _wib(2026, 7, 16, 16, 0)  # before the 20:00 WIB cutoff
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=date(2026, 7, 15),
        )

        assert result.status is SourceAvailabilityStatus.LATE
        assert result.is_authoritative is False
        assert result.expected_available_at == datetime(2026, 7, 16, 20, 0, tzinfo=IDX_TIMEZONE)
        assert any("has not yet passed" in note for note in result.notes)

    def test_broker_source_one_session_behind_after_cutoff_stays_late_not_stale(self, use_case):
        """Chosen DQ-002H rule: the cutoff having passed does NOT demote a
        source that is still within its configured settlement lag to STALE
        — it stays LATE, with an explicit note that the cutoff has passed."""
        decision_at = _wib(2026, 7, 16, 21, 0)  # after the 20:00 WIB cutoff
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=date(2026, 7, 15),
        )

        assert result.status is SourceAvailabilityStatus.LATE
        assert result.is_authoritative is False
        assert result.expected_available_at == datetime(2026, 7, 16, 20, 0, tzinfo=IDX_TIMEZONE)
        assert any("has passed" in note and "remains within" in note for note in result.notes)

    def test_broker_source_beyond_configured_lag_is_stale_regardless_of_cutoff(self, use_case):
        decision_at = _wib(2026, 7, 16, 21, 0)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="broker_daily_flow",
            effective_session=session,
            observed_through=date(2026, 7, 14),  # 2 sessions behind, lag is 1
        )

        assert result.status is SourceAvailabilityStatus.STALE
        assert result.is_authoritative is False
        assert result.expected_available_at == datetime(2026, 7, 16, 20, 0, tzinfo=IDX_TIMEZONE)

    def test_candles_one_session_behind_has_no_cutoff_metadata(self, use_case):
        """Candles have no provider_cutoff_time configured — broker cutoff
        behavior/metadata must never leak onto candles."""
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="candles",
            effective_session=session,
            observed_through=date(2026, 7, 15),
        )

        assert result.status is SourceAvailabilityStatus.STALE
        assert result.expected_available_at is None
        assert not any("cutoff" in note.lower() for note in result.notes)

    def test_future_broker_row_has_no_cutoff_metadata(self, use_case):
        """A future/invalid observation must never carry cutoff metadata —
        the future-row guard is not weakened by adding cutoff policy."""
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=date(2026, 7, 17),
        )

        assert result.status is SourceAvailabilityStatus.INVALID
        assert result.is_authoritative is False
        assert result.expected_available_at is None

    def test_current_broker_source_has_no_cutoff_metadata(self, use_case):
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        result = use_case.execute(
            source_family="broker_summaries",
            effective_session=session,
            observed_through=date(2026, 7, 16),
        )

        assert result.status is SourceAvailabilityStatus.CURRENT
        assert result.expected_available_at is None

    def test_registry_rejects_provider_cutoff_on_non_session_aligned_rule(self):
        with pytest.raises(ValueError):
            SourceSettlementRule(
                source_family="analyst_cache",
                settlement_basis=SettlementBasis.FETCH_TIMESTAMP,
                is_authoritative_capable=True,
                provider_cutoff_time=datetime(2026, 1, 1, 20, 0).time(),
            )


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

    def test_fetch_timestamp_sources_are_unaffected_by_provider_cutoff_fields(self, use_case):
        """DQ-002H: `expected_available_at`/cutoff notes are SESSION_ALIGNED-
        only concepts; FETCH_TIMESTAMP sources must never carry them, whether
        CURRENT or STALE."""
        decision_at = _wib(2026, 7, 16)
        session = _session(date(2026, 7, 16), decision_at)

        current = use_case.execute(
            source_family="analyst_cache",
            effective_session=session,
            available_at=_wib(2026, 7, 10),
        )
        stale = use_case.execute(
            source_family="seasonality_cache",
            effective_session=session,
            available_at=_wib(2026, 1, 1),
        )

        assert current.status is SourceAvailabilityStatus.CURRENT
        assert current.expected_available_at is None
        assert stale.status is SourceAvailabilityStatus.STALE
        assert stale.expected_available_at is None
        assert not any("cutoff" in note.lower() for note in stale.notes)


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
        assert result.expected_available_at is None  # DQ-002H: no cutoff concept for sentiment

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

    def test_sentiment_cannot_be_swapped_in_as_authoritative_via_custom_registry(self, use_case):
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
