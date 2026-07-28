"""Parser + category + fallback-id tests for Stockbit economic calendar."""

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from src.domain.value_objects.macro_calendar_event import MacroEventCategory
from src.infrastructure.browser.stockbit_macro_calendar_parsers import (
    _fallback_id,
    parse_economic_body,
    parse_economic_item,
)
from src.infrastructure.config.macro_calendar_config import (
    MacroCalendarConfig,
    MacroCategoryRule,
    normalize_macro_category,
)

FIXTURE = (
    Path(__file__).resolve().parents[2] / "fixtures" / "stockbit" / "economic_calendar_sample.json"
)


@pytest.fixture
def sample_body() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestFallbackId:
    def test_deterministic_and_matches_hand_hash(self):
        raw = {"econcal_item": "GDP Growth YoY", "econcal_date": "2026-06-15"}
        composite = (
            f"economic|2026-06-15|GDP Growth YoY|{json.dumps(raw, sort_keys=True, default=str)}"
        )
        expected = hashlib.sha256(composite.encode()).hexdigest()
        assert _fallback_id("2026-06-15", "GDP Growth YoY", raw) == expected
        assert _fallback_id("2026-06-15", "GDP Growth YoY", raw) == _fallback_id(
            "2026-06-15", "GDP Growth YoY", raw
        )


class TestNormalizeCategory:
    def test_bi_rate(self):
        assert normalize_macro_category("BI 7-Day Reverse Repo Rate") == MacroEventCategory.BI_RATE

    def test_inflation(self):
        assert normalize_macro_category("CPI YoY") == MacroEventCategory.INFLATION

    def test_growth(self):
        assert normalize_macro_category("GDP Growth YoY") == MacroEventCategory.GROWTH

    def test_unknown_is_other(self):
        assert normalize_macro_category("Car Sales YoY") == MacroEventCategory.OTHER

    def test_first_match_wins(self):
        cfg = MacroCalendarConfig(
            category_rules=(
                MacroCategoryRule(MacroEventCategory.BI_RATE, ("Rate",)),
                MacroCategoryRule(MacroEventCategory.INFLATION, ("Rate",)),
            ),
            default_category=MacroEventCategory.OTHER,
        )
        assert normalize_macro_category("Rate Decision", cfg) == MacroEventCategory.BI_RATE


class TestParseEconomicBody:
    def test_fixture_parses_usable_rows_skips_bad(self, sample_body):
        events = parse_economic_body(sample_body, fetched_at="2026-07-11T00:00:00")
        # 5 items in fixture; 1 missing date → 4 events
        assert len(events) == 4
        by_id = {e.source_event_id: e for e in events}
        assert by_id["1001"].category == MacroEventCategory.BI_RATE
        assert by_id["1001"].actual == "5.50%"
        assert by_id["1002"].category == MacroEventCategory.INFLATION
        assert by_id["1003"].category == MacroEventCategory.OTHER
        assert by_id["1003"].title == "Car Sales YoY"
        # empty econcal_id → fallback hash
        gdp = [e for e in events if e.title == "GDP Growth YoY"][0]
        assert len(gdp.source_event_id) == 64
        assert gdp.category == MacroEventCategory.GROWTH
        assert gdp.event_date == date(2026, 6, 15)
        assert gdp.timezone == "7"

    def test_missing_economic_list_raises(self):
        with pytest.raises(ValueError, match="economic"):
            parse_economic_body({"data": {}}, fetched_at="t")

    def test_parse_item_missing_title_returns_none(self):
        assert (
            parse_economic_item(
                {"econcal_id": "1", "econcal_date": "2026-01-01", "econcal_item": ""},
                fetched_at="t",
            )
            is None
        )
