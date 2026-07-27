"""
Shared status-string policy for `saham fetch market` update output.

Decides the display status token for a ticker's candle/broker/summary update
based on how many rows were added and the resulting cached date range. Pure
string formatting: no I/O, no infrastructure imports.

Layer: Application
"""

from datetime import date


def cached_status(latest: date, end_date: date) -> str:
    """Return an explicit cache status for update output."""
    lag_days = (end_date - latest).days
    if lag_days <= 0:
        return f"✓({latest})"
    return f"cached({lag_days}d lag)"


def no_new_data_status(latest: date | None) -> str:
    if latest is None:
        return "no-data"
    return f"up-to-date({latest.isoformat()})"


def is_cached_status(status: str) -> bool:
    return status.startswith("✓(")


def broker_update_status(
    added_count: int,
    updated_range: tuple[date, date] | None,
    fetch_modes: set[str],
) -> str:
    """Return an explicit broker update status for update output."""
    if added_count == 0 and updated_range is None:
        return "no-data"

    span_days = (updated_range[1] - updated_range[0]).days + 1 if updated_range else 0
    prefix = "backfill+" if "backfill" in fetch_modes else "+"
    return f"{prefix}{added_count}rows/span={span_days}d"


def range_update_status(
    added_count: int,
    updated_range: tuple[date, date] | None,
    fetch_modes: set[str],
) -> str:
    """Return an explicit cache update status for date-ranged data."""
    if added_count == 0 and updated_range is None:
        return "no-data"

    span_days = (updated_range[1] - updated_range[0]).days + 1 if updated_range else 0
    prefix = "backfill+" if "backfill" in fetch_modes else "+"
    return f"{prefix}{added_count}rows/span={span_days}d"
