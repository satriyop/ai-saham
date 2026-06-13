"""Tests for update command helper behavior."""

from datetime import date
from pathlib import Path

from src.adapters.cli.update_commands import (
    _cached_status,
    _fetch_broker,
    _is_cached_status,
    _no_new_data_status,
)


def test_cached_status_reports_exact_cache_age():
    assert _cached_status(date(2026, 6, 13), date(2026, 6, 13)) == "cached-current"


def test_is_cached_status_matches_explicit_cache_statuses():
    assert _is_cached_status("cached-current") is True
    assert _is_cached_status("provider-no-new-data(latest=2026-06-10)") is False
    assert _is_cached_status("+2d") is False
    assert _is_cached_status("ERR:timeout") is False


def test_no_new_data_status_reports_provider_check_result():
    assert (
        _no_new_data_status(date(2026, 6, 10))
        == "up-to-date(2026-06-10)"
    )
    assert _no_new_data_status(None) == "no-data"


def test_fetch_broker_skips_index_ticker(tmp_path: Path):
    status = _fetch_broker(
        ticker="^JKSE",
        days=90,
        db_path=tmp_path / "data.db",
        broker_provider=object(),
        refresh=False,
    )

    assert status == "n/a:index"
