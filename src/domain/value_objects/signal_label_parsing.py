"""Primitive parsing utilities for signal labels and fingerprints."""

from datetime import date, datetime
from typing import Any


def _parse_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _parse_optional_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    return _parse_date(value)


def _parse_optional_datetime(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)
