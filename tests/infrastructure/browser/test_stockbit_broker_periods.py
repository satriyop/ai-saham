"""Tests for pure Stockbit broker period-enum mapping."""

from datetime import date, timedelta

from src.infrastructure.browser.stockbit_broker_periods import (
    broker_summary_period_for_range,
    foreign_top_period_for_range,
)

_START = date(2026, 1, 1)


def _range(days: int) -> tuple[date, date]:
    return _START, _START + timedelta(days=days)


# ── broker_summary_period_for_range ────────────────────────────────────────


def test_broker_summary_period_1_day():
    assert broker_summary_period_for_range(*_range(1)) == "BROKER_SUMMARY_PERIOD_LATEST"


def test_broker_summary_period_7_days():
    assert broker_summary_period_for_range(*_range(7)) == "BROKER_SUMMARY_PERIOD_LAST_7_DAYS"


def test_broker_summary_period_30_days():
    assert broker_summary_period_for_range(*_range(30)) == "BROKER_SUMMARY_PERIOD_LAST_1_MONTH"


def test_broker_summary_period_90_days():
    assert broker_summary_period_for_range(*_range(90)) == "BROKER_SUMMARY_PERIOD_LAST_3_MONTHS"


def test_broker_summary_period_180_days():
    assert broker_summary_period_for_range(*_range(180)) == "BROKER_SUMMARY_PERIOD_LAST_6_MONTHS"


def test_broker_summary_period_beyond_180_days():
    assert broker_summary_period_for_range(*_range(181)) == "BROKER_SUMMARY_PERIOD_LAST_1_YEAR"


# ── foreign_top_period_for_range ───────────────────────────────────────────


def test_foreign_top_period_1_day():
    assert foreign_top_period_for_range(*_range(1)) == "RT_PERIOD_LAST_1_DAY"


def test_foreign_top_period_3_days():
    assert foreign_top_period_for_range(*_range(3)) == "RT_PERIOD_LAST_3_DAYS"


def test_foreign_top_period_7_days():
    assert foreign_top_period_for_range(*_range(7)) == "RT_PERIOD_LAST_7_DAYS"


def test_foreign_top_period_30_days():
    assert foreign_top_period_for_range(*_range(30)) == "RT_PERIOD_LAST_1_MONTH"


def test_foreign_top_period_90_days():
    assert foreign_top_period_for_range(*_range(90)) == "RT_PERIOD_LAST_3_MONTHS"


def test_foreign_top_period_beyond_90_days():
    assert foreign_top_period_for_range(*_range(91)) == "RT_PERIOD_LAST_1_YEAR"
