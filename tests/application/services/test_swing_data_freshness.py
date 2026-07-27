"""Tests for swing analysis data freshness — DQ-002C.

build_swing_data_freshness consumes an already-resolved EffectiveMarketSession
and owns no weekday/wall-clock arithmetic of its own (that behavior belongs
to EffectiveMarketSessionResolver — see test_effective_market_session_resolver.py).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.application.services.effective_market_session_resolver import (
    EffectiveMarketSession,
)
from src.application.services.swing_data_freshness import build_swing_data_freshness

_WIB = ZoneInfo("Asia/Jakarta")


class FakeRangeRepo:
    def __init__(self, ranges):
        self._ranges = ranges

    def get_date_range(self, ticker):
        return self._ranges.get(ticker)


def _session(
    *,
    latest_completed_session: date | None,
    is_eod_pending: bool,
    decision_at: datetime | None = None,
) -> EffectiveMarketSession:
    decision_at = decision_at or datetime(2026, 6, 28, 16, 30, tzinfo=_WIB)
    return EffectiveMarketSession(
        run_at=decision_at,
        decision_at=decision_at,
        latest_completed_session=latest_completed_session,
        analysis_as_of=latest_completed_session,
        market_session_name="AFTER_CLOSE",
        is_eod_pending=is_eod_pending,
        resolution_source="test_fixture",
        notes=(),
    )


def test_weekend_or_holiday_case_uses_resolved_session_not_stale():
    # effective_session already rolled back to Thursday (weekend/holiday-aware
    # cache resolution) — Thursday-dated cached data must not warn stale.
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=date(2026, 6, 25), is_eod_pending=False
        ),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
    )

    assert freshness.candle_end == date(2026, 6, 25)
    assert freshness.warnings == ()


def test_before_close_live_case_prior_session_data_does_not_warn_stale():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(latest_completed_session=date(2026, 6, 25), is_eod_pending=True),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
    )

    assert freshness.warnings == ()


def test_after_close_same_day_case_previous_day_source_warns_stale():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=date(2026, 6, 26), is_eod_pending=False
        ),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
    )

    assert any("candle" in w and "stale" in w for w in freshness.warnings)
    assert any("broker flow" in w and "stale" in w for w in freshness.warnings)


def test_unknown_latest_completed_session_warns_unknown_without_weekday_fallback():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(latest_completed_session=None, is_eod_pending=False),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
    )

    assert any("unknown" in w.lower() for w in freshness.warnings)
    assert not any("stale" in w for w in freshness.warnings)


def test_candle_broker_mismatch_warning_still_appears():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=date(2026, 6, 25), is_eod_pending=False
        ),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 2), date(2026, 6, 24))}),
    )

    assert any("differ" in w for w in freshness.warnings)


def test_refresh_err_warning_still_appears():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=date(2026, 6, 25), is_eod_pending=False
        ),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        refresh_actions=("broker(idx)=ERR:auth",),
    )

    assert any("Refresh issue: broker(idx)=ERR:auth" in w for w in freshness.warnings)


def test_missing_candle_data_warns_no_cached_data():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=date(2026, 6, 25), is_eod_pending=False
        ),
        market_repo=FakeRangeRepo({}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
    )

    assert any("No cached candle data" in w for w in freshness.warnings)


def test_source_date_newer_than_expected_does_not_warn_stale():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=date(2026, 6, 24), is_eod_pending=False
        ),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
    )

    assert not any("stale" in w for w in freshness.warnings)


def test_as_of_date_uses_analysis_as_of_from_effective_session():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=date(2026, 6, 25), is_eod_pending=False
        ),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
    )

    assert freshness.as_of_date == date(2026, 6, 25)


def test_as_of_date_falls_back_to_decision_at_date_when_session_unresolved():
    decision_at = datetime(2026, 6, 28, 16, 30, tzinfo=_WIB)
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=None, is_eod_pending=False, decision_at=decision_at
        ),
        market_repo=FakeRangeRepo({}),
        broker_repo=FakeRangeRepo({}),
    )

    assert freshness.as_of_date == date(2026, 6, 28)


def test_to_dict_shape_unchanged():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        effective_session=_session(
            latest_completed_session=date(2026, 6, 25), is_eod_pending=False
        ),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 2), date(2026, 6, 25))}),
        refresh_actions=("candles=provider-no-new-data(latest=2026-06-25)",),
    )

    data = freshness.to_dict()
    assert data["as_of_date"] == "2026-06-25"
    assert data["candles_through"] == "2026-06-25"
    assert data["broker_flow_through"] == "2026-06-25"
    assert data["refresh_actions"] == ["candles=provider-no-new-data(latest=2026-06-25)"]
