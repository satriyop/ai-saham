"""Tests for swing_flow_detail_builder.py."""

from datetime import date
from decimal import Decimal

from src.application.services.swing_flow_detail_builder import build_flow_detail


class _FakeBrokerRepo:
    def __init__(self, summaries):
        self._summaries = summaries

    def get_broker_summaries(self, ticker, end_date=None):
        return self._summaries


def _fake_summary(day, foreign_net, is_buy, ratio=5.0):
    """Minimal mock with required attributes for build_flow_detail."""

    class _FakeSummary:
        def __init__(self, day, foreign_net, is_buy, ratio):
            self.date = day
            self.foreign_net_value = Decimal(str(foreign_net))
            self.is_foreign_accumulating = is_buy
            self.foreign_flow_ratio = Decimal(str(ratio))

    return _FakeSummary(day, foreign_net, is_buy, ratio)


def test_no_summaries_returns_none():
    result = build_flow_detail(
        "BBCA",
        _FakeBrokerRepo([]),
        window_sessions=5,
        as_of_date=date(2026, 6, 10),
    )
    assert result is None


def test_total_net_flow_buy_sessions_sell_sessions():
    summaries = [
        _fake_summary(date(2026, 6, 1), 50000000, True, 5.0),
        _fake_summary(date(2026, 6, 2), -20000000, False, -2.0),
        _fake_summary(date(2026, 6, 3), 30000000, True, 3.0),
    ]
    result = build_flow_detail(
        "BBCA",
        _FakeBrokerRepo(summaries),
        window_sessions=5,
        as_of_date=date(2026, 6, 3),
    )
    assert result is not None
    assert result.total_net_flow == Decimal("60000000")
    assert result.buy_sessions == 2
    assert result.sell_sessions == 1
    assert result.available_sessions == 3


def test_consecutive_buy_sessions_from_end():
    summaries = [
        _fake_summary(date(2026, 6, 1), 50000000, False, -5.0),
        _fake_summary(date(2026, 6, 2), 20000000, True, 2.0),
        _fake_summary(date(2026, 6, 3), 30000000, True, 3.0),
    ]
    result = build_flow_detail(
        "BBCA",
        _FakeBrokerRepo(summaries),
        window_sessions=5,
        as_of_date=date(2026, 6, 3),
    )
    assert result is not None
    assert result.consecutive_buy_sessions == 2


def test_average_flow_ratio_and_latest_fields():
    summaries = [
        _fake_summary(date(2026, 6, 1), 10000000, True, 2.0),
        _fake_summary(date(2026, 6, 2), 30000000, True, 6.0),
    ]
    result = build_flow_detail(
        "BBCA",
        _FakeBrokerRepo(summaries),
        window_sessions=5,
        as_of_date=date(2026, 6, 2),
    )
    assert result is not None
    assert result.avg_flow_ratio_pct == 4.0
    assert result.latest_net_flow == Decimal("30000000")
    assert result.latest_flow_ratio_pct == 6.0
    assert result.latest_date == date(2026, 6, 2)
    assert result.from_date == date(2026, 6, 1)
    assert result.through_date == date(2026, 6, 2)
    assert result.window_sessions == 5


def test_window_sessions_limit():
    summaries = [
        _fake_summary(date(2026, 6, day), 10000000, True, 1.0)
        for day in range(1, 11)
    ]
    result = build_flow_detail(
        "BBCA",
        _FakeBrokerRepo(summaries),
        window_sessions=3,
        as_of_date=date(2026, 6, 10),
    )
    assert result is not None
    assert result.available_sessions == 3
    assert result.from_date == date(2026, 6, 8)
    assert result.through_date == date(2026, 6, 10)
