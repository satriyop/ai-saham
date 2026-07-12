from datetime import date

from src.adapters.cli.fetch_market_commands import (
    _broker_update_status,
    _cached_status,
    _is_cached_status,
    _no_new_data_status,
    _range_update_status,
)


def test_cached_status_reports_exact_cache_age():
    assert _cached_status(date(2026, 6, 13), date(2026, 6, 13)) == "✓(2026-06-13)"


def test_is_cached_status_matches_explicit_cache_statuses():
    assert _is_cached_status("✓(2026-06-13)") is True
    assert _is_cached_status("✓(2026-06-10)") is True
    assert _is_cached_status("provider-no-new-data(latest=2026-06-10)") is False
    assert _is_cached_status("+2d") is False
    assert _is_cached_status("ERR:timeout") is False
    assert _is_cached_status("cached-current") is False


def test_no_new_data_status_reports_provider_check_result():
    assert (
        _no_new_data_status(date(2026, 6, 10))
        == "up-to-date(2026-06-10)"
    )
    assert _no_new_data_status(None) == "no-data"


def test_broker_update_status_distinguishes_rows_from_calendar_span():
    assert _broker_update_status(
        added_count=11,
        updated_range=(date(2025, 6, 14), date(2026, 6, 14)),
        fetch_modes={"backfill"},
    ) == "backfill+11rows/span=366d"
    assert _broker_update_status(0, None, {"initial"}) == "no-data"


def test_range_update_status_distinguishes_rows_from_calendar_span():
    assert _range_update_status(
        added_count=11,
        updated_range=(date(2025, 6, 14), date(2026, 6, 14)),
        fetch_modes={"backfill"},
    ) == "backfill+11rows/span=366d"
    assert _range_update_status(0, None, {"initial"}) == "no-data"
