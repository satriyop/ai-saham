"""
Tests for corporate action calendar value objects (domain layer, zero I/O).

Covers:
- CorporateActionCalendarEvent.__post_init__ validation (source_event_id,
  ticker required; ticker normalized to uppercase)
- Frozen dataclass immutability for both CorporateActionCalendarEvent and
  CorporateActionCalendarDate
- CorporateActionType enum membership (exactly the 9 supported v1 types;
  "warrant"/"economic" are NOT members — this is the whole enforcement
  mechanism that keeps unsupported types out of default type lists)
"""

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionCalendarDate,
    CorporateActionCalendarEvent,
    CorporateActionDateRole,
    CorporateActionType,
)


def _date_row(role: CorporateActionDateRole = CorporateActionDateRole.EX_DATE) -> CorporateActionCalendarDate:
    return CorporateActionCalendarDate(date_role=role, event_date=date(2026, 7, 15))


def _event(**overrides) -> CorporateActionCalendarEvent:
    kwargs = dict(
        event_type=CorporateActionType.DIVIDEND,
        source_event_id="abc123",
        ticker="bbca",
        dates=(_date_row(),),
    )
    kwargs.update(overrides)
    return CorporateActionCalendarEvent(**kwargs)


class TestCorporateActionCalendarEventValidation:
    def test_empty_source_event_id_raises(self):
        with pytest.raises(ValueError, match="source_event_id"):
            _event(source_event_id="")

    def test_empty_ticker_raises(self):
        with pytest.raises(ValueError, match="ticker"):
            _event(ticker="")

    def test_ticker_is_uppercased(self):
        event = _event(ticker="bbca")
        assert event.ticker == "BBCA"

    def test_ticker_already_uppercase_is_unaffected(self):
        event = _event(ticker="BBRI")
        assert event.ticker == "BBRI"

    def test_defaults(self):
        event = _event()
        assert event.source == "stockbit"
        assert event.company_id is None
        assert event.active is False
        assert event.raw_payload_json == "{}"
        assert event.fetched_at == ""


class TestFrozenImmutability:
    def test_event_mutation_raises(self):
        event = _event()
        with pytest.raises(FrozenInstanceError):
            event.ticker = "BMRI"  # type: ignore[misc]

    def test_date_mutation_raises(self):
        d = _date_row()
        with pytest.raises(FrozenInstanceError):
            d.event_date = date(2026, 1, 1)  # type: ignore[misc]


class TestCorporateActionTypeEnum:
    """warrant/economic are NOT supported — the enum membership check is the
    entire enforcement mechanism (no separate allow-list needed elsewhere)."""

    def test_exactly_nine_supported_types(self):
        assert len(CorporateActionType) == 9

    def test_all_nine_values_present(self):
        values = {t.value for t in CorporateActionType}
        assert values == {
            "dividend",
            "stock_split",
            "reverse_split",
            "rights_issue",
            "bonus",
            "tender_offer",
            "rups",
            "pubex",
            "ipo",
        }

    def test_warrant_is_not_a_member(self):
        with pytest.raises(ValueError):
            CorporateActionType("warrant")

    def test_economic_is_not_a_member(self):
        with pytest.raises(ValueError):
            CorporateActionType("economic")


class TestCorporateActionDateRoleEnum:
    def test_expected_roles_present(self):
        values = {r.value for r in CorporateActionDateRole}
        assert "cum_date" in values
        assert "ex_date" in values
        assert "recording_date" in values
        assert "payment_date" in values
        assert "subscription_date" in values
        assert "rups_date" in values
        assert "pubex_date" in values
        assert "listing_date" in values
