"""
Tests for macro calendar value objects (domain layer, zero I/O).
"""

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from src.domain.value_objects.macro_calendar_event import (
    MacroCalendarEvent,
    MacroEventCategory,
)


def _event(**overrides) -> MacroCalendarEvent:
    kwargs = dict(
        source_event_id="e1",
        event_date=date(2026, 7, 10),
        category=MacroEventCategory.OTHER,
        title="Car Sales YoY",
    )
    kwargs.update(overrides)
    return MacroCalendarEvent(**kwargs)


class TestMacroCalendarEventValidation:
    def test_empty_source_event_id_raises(self):
        with pytest.raises(ValueError, match="source_event_id"):
            _event(source_event_id="")

    def test_whitespace_source_event_id_raises(self):
        with pytest.raises(ValueError, match="source_event_id"):
            _event(source_event_id="   ")

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="title"):
            _event(title="")

    def test_title_is_stripped(self):
        event = _event(title="  CPI YoY  ")
        assert event.title == "CPI YoY"

    def test_defaults(self):
        event = _event()
        assert event.source == "stockbit"
        assert event.country == "ID"
        assert event.actual is None
        assert event.raw_payload_json == "{}"
        assert event.fetched_at == ""

    def test_empty_country_defaults_to_id(self):
        event = _event(country="")
        assert event.country == "ID"


class TestMacroEventCategory:
    def test_known_members(self):
        assert {c.value for c in MacroEventCategory} == {
            "bi_rate",
            "inflation",
            "growth",
            "trade",
            "other",
        }


class TestFrozenImmutability:
    def test_event_mutation_raises(self):
        event = _event()
        with pytest.raises(FrozenInstanceError):
            event.title = "X"  # type: ignore[misc]
