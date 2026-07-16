"""Tests for MarketFreshnessService — cache-tolerance policy, no infrastructure."""

from datetime import date, datetime

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.market_freshness_service import MarketFreshnessService
from src.domain.value_objects.idx_market import IDX_TIMEZONE


def _session(latest_completed_session: date | None) -> EffectiveMarketSession:
    now = datetime(2026, 6, 15, 16, 0, tzinfo=IDX_TIMEZONE)
    return EffectiveMarketSession(
        run_at=now,
        decision_at=now,
        latest_completed_session=latest_completed_session,
        analysis_as_of=latest_completed_session,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=False,
        resolution_source="ihsg_cache_same_day",
    )


def test_resolve_reference_trading_day_uses_effective_session_latest_completed():
    service = MarketFreshnessService()
    session = _session(date(2026, 6, 19))

    assert service.resolve_reference_trading_day(session, date(2026, 6, 20)) == date(2026, 6, 19)


def test_resolve_reference_trading_day_falls_back_to_last_weekday_when_unresolved():
    service = MarketFreshnessService()
    session = _session(None)

    # Saturday 2026-06-20 -> Friday 2026-06-19
    assert service.resolve_reference_trading_day(session, date(2026, 6, 20)) == date(2026, 6, 19)


def test_end_tolerance_days_uses_weekday_fallback_for_benchmark_itself():
    service = MarketFreshnessService()
    # Stale/older session must be ignored for the benchmark itself.
    session = _session(date(2020, 1, 1))

    tolerance = service.end_tolerance_days(
        is_benchmark=True, effective_session=session, today=date(2026, 6, 15)
    )
    assert tolerance == 0


def test_end_tolerance_days_computed_from_effective_session_for_other_tickers():
    service = MarketFreshnessService()
    session = _session(date(2026, 6, 10))

    tolerance = service.end_tolerance_days(
        is_benchmark=False, effective_session=session, today=date(2026, 6, 15)
    )
    assert tolerance == 5


def test_end_tolerance_days_never_negative():
    service = MarketFreshnessService()
    session = _session(date(2026, 6, 15))

    tolerance = service.end_tolerance_days(
        is_benchmark=False, effective_session=session, today=date(2026, 6, 15)
    )
    assert tolerance == 0
