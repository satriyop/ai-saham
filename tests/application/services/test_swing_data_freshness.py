from datetime import date

from src.application.services.swing_data_freshness import (
    build_swing_data_freshness,
    expected_weekday_data_date,
    weekday_session_lag,
)


class FakeRangeRepo:
    def __init__(self, ranges):
        self._ranges = ranges

    def get_date_range(self, ticker):
        return self._ranges.get(ticker)


def test_expected_weekday_data_date_uses_friday_for_weekend():
    assert expected_weekday_data_date(date(2026, 6, 26)) == date(2026, 6, 26)
    assert expected_weekday_data_date(date(2026, 6, 27)) == date(2026, 6, 26)
    assert expected_weekday_data_date(date(2026, 6, 28)) == date(2026, 6, 26)


def test_weekday_session_lag_counts_only_weekdays():
    assert weekday_session_lag(date(2026, 6, 25), date(2026, 6, 28)) == 1
    assert weekday_session_lag(date(2026, 6, 26), date(2026, 6, 28)) == 0


def test_build_swing_data_freshness_reports_lag_and_refresh_errors():
    freshness = build_swing_data_freshness(
        ticker="BBCA",
        as_of_date=date(2026, 6, 28),
        market_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        broker_repo=FakeRangeRepo({"BBCA": (date(2026, 1, 1), date(2026, 6, 25))}),
        refresh_actions=("broker(idx)=ERR:auth",),
    )

    assert freshness.candle_end == date(2026, 6, 25)
    assert freshness.broker_end == date(2026, 6, 25)
    assert any("Latest candle is 1 trading session" in w for w in freshness.warnings)
    assert any("Latest broker flow is 1 trading session" in w for w in freshness.warnings)
    assert any("Refresh issue: broker(idx)=ERR:auth" in w for w in freshness.warnings)
