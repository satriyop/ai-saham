from datetime import date

from src.application.services.fetch_market_status_policy import (
    broker_update_status,
    cached_status,
    is_cached_status,
    no_new_data_status,
    range_update_status,
)


def test_cached_status_reports_exact_cache_age():
    assert cached_status(date(2026, 6, 13), date(2026, 6, 13)) == "✓(2026-06-13)"


def test_is_cached_status_matches_explicit_cache_statuses():
    assert is_cached_status("✓(2026-06-13)") is True
    assert is_cached_status("✓(2026-06-10)") is True
    assert is_cached_status("provider-no-new-data(latest=2026-06-10)") is False
    assert is_cached_status("+2d") is False
    assert is_cached_status("ERR:timeout") is False
    assert is_cached_status("cached-current") is False


def test_no_new_data_status_reports_provider_check_result():
    assert (
        no_new_data_status(date(2026, 6, 10))
        == "up-to-date(2026-06-10)"
    )
    assert no_new_data_status(None) == "no-data"


def test_broker_update_status_distinguishes_rows_from_calendar_span():
    assert broker_update_status(
        added_count=11,
        updated_range=(date(2025, 6, 14), date(2026, 6, 14)),
        fetch_modes={"backfill"},
    ) == "backfill+11rows/span=366d"
    assert broker_update_status(0, None, {"initial"}) == "no-data"


def test_range_update_status_distinguishes_rows_from_calendar_span():
    assert range_update_status(
        added_count=11,
        updated_range=(date(2025, 6, 14), date(2026, 6, 14)),
        fetch_modes={"backfill"},
    ) == "backfill+11rows/span=366d"
    assert range_update_status(0, None, {"initial"}) == "no-data"
