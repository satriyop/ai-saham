"""
Per-type parser tests (batch B): tender_offer, rups, pubex, ipo.

See test_stockbit_corporate_action_calendar_parsers_a.py docstring for the
cross-cutting-guard note (this batch doesn't re-verify company_symbol/ticker/
company_id/date-parsing guards, which are covered once in
test_stockbit_corporate_action_calendar.py).
"""

from __future__ import annotations

from src.domain.value_objects.corporate_action_calendar import (
    CorporateActionDateRole,
    CorporateActionType,
)
from src.infrastructure.browser.stockbit_corporate_action_calendar import (
    StockbitCorporateActionCalendarProvider,
)

BASE = "https://exodus.stockbit.com/corpaction"


class FakeApiClient:
    def __init__(self, bodies: dict[str, dict | None]) -> None:
        self._bodies = bodies

    def get(self, url: str, params=None):
        return self._bodies.get(url)


def _provider(url: str, body: dict) -> StockbitCorporateActionCalendarProvider:
    return StockbitCorporateActionCalendarProvider(api_client=FakeApiClient({url: body}))


def _roles(event) -> set[CorporateActionDateRole]:
    return {d.date_role for d in event.dates}


# ── tender_offer ─────────────────────────────────────────────────────────────


class TestTenderOfferParser:
    URL = f"{BASE}/tenderoffer"

    def _fetch(self, item: dict):
        provider = _provider(self.URL, {"data": {"tender": [item]}})
        return provider.fetch_events((CorporateActionType.TENDER_OFFER,))

    def test_list_key_is_tender(self):
        item = {
            "company_symbol": "BBCA",
            "tender_id": "t1",
            "tender_start": "2026-07-09",
            "tender_end": "2026-08-07",
            "tender_paydate": "2026-08-14",
            "tender_price": "523",
        }
        events = self._fetch(item)
        assert len(events) == 1
        ev = events[0]
        assert ev.source_event_id == "t1"
        assert _roles(ev) == {
            CorporateActionDateRole.OFFER_START,
            CorporateActionDateRole.OFFER_END,
            CorporateActionDateRole.PAYMENT_DATE,
        }
        assert ev.price == "523"

    def test_wrong_list_key_yields_nothing(self):
        item = {"company_symbol": "BBCA", "tender_id": "t1"}
        provider = _provider(self.URL, {"data": {"tenderoffer": [item]}})
        assert provider.fetch_events((CorporateActionType.TENDER_OFFER,)) == []

    def test_price_empty_string_is_none(self):
        item = {"company_symbol": "BBCA", "tender_id": "t1", "tender_price": ""}
        events = self._fetch(item)
        assert events[0].price is None

    def test_company_name_is_captured(self):
        item = {"company_symbol": "BBCA", "tender_id": "t1", "company_name": "Bank Central Asia"}
        events = self._fetch(item)
        assert events[0].company_name == "Bank Central Asia"


# ── rups ─────────────────────────────────────────────────────────────────────


class TestRupsParser:
    URL = f"{BASE}/rups"

    def _fetch(self, item: dict):
        provider = _provider(self.URL, {"data": {"rups": [item]}})
        return provider.fetch_events((CorporateActionType.RUPS,))

    def test_rups_time_attaches_as_event_time_only_on_rups_date_role(self):
        item = {
            "company_symbol": "BBCA",
            "rups_id": "r1",
            "rups_date": "2026-08-18",
            "rups_time": "10:00",
            "rups_eligible_date": "2026-07-22",
        }
        events = self._fetch(item)
        ev = events[0]
        rups_date_row = next(
            d for d in ev.dates if d.date_role == CorporateActionDateRole.RUPS_DATE
        )
        eligible_row = next(
            d for d in ev.dates if d.date_role == CorporateActionDateRole.ELIGIBLE_DATE
        )
        assert rups_date_row.event_time == "10:00"
        assert eligible_row.event_time is None

    def test_event_note_is_always_none_even_with_rups_venue_present(self):
        """venue is explicitly NOT stored as event_note per schema — assert
        this explicitly since it's an easy field to accidentally wire up."""
        item = {
            "company_symbol": "BBCA",
            "rups_id": "r1",
            "rups_date": "2026-08-18",
            "rups_venue": "Kantor Pusat Jl. Sudirman",
        }
        events = self._fetch(item)
        assert events[0].event_note is None

    def test_missing_rups_time_leaves_event_time_none(self):
        item = {"company_symbol": "BBCA", "rups_id": "r1", "rups_date": "2026-08-18"}
        events = self._fetch(item)
        rups_date_row = next(
            d for d in events[0].dates if d.date_role == CorporateActionDateRole.RUPS_DATE
        )
        assert rups_date_row.event_time is None

    def test_company_name_is_captured(self):
        item = {"company_symbol": "BBCA", "rups_id": "r1", "company_name": "Bank Central Asia"}
        events = self._fetch(item)
        assert events[0].company_name == "Bank Central Asia"


# ── pubex ────────────────────────────────────────────────────────────────────


class TestPubexParser:
    URL = f"{BASE}/pubex"

    def _fetch(self, item: dict):
        provider = _provider(self.URL, {"data": {"pubex": [item]}})
        return provider.fetch_events((CorporateActionType.PUBEX,))

    def test_single_role_pubex_date_with_puexp_time(self):
        item = {
            "company_symbol": "BBCA",
            "puexp_id": "p1",
            "puexp_date": "2026-07-23",
            "puexp_time": "15:00:00",
        }
        events = self._fetch(item)
        ev = events[0]
        assert len(ev.dates) == 1
        assert ev.dates[0].date_role == CorporateActionDateRole.PUBEX_DATE
        assert ev.dates[0].event_time == "15:00:00"

    def test_event_note_always_none(self):
        item = {
            "company_symbol": "BBCA",
            "puexp_id": "p1",
            "puexp_date": "2026-07-23",
            "puexp_venue": "dilakukan secara online",
        }
        events = self._fetch(item)
        assert events[0].event_note is None

    def test_missing_puexp_time_leaves_event_time_none(self):
        item = {"company_symbol": "BBCA", "puexp_id": "p1", "puexp_date": "2026-07-23"}
        events = self._fetch(item)
        assert events[0].dates[0].event_time is None


# ── ipo ──────────────────────────────────────────────────────────────────────


class TestIpoParser:
    URL = f"{BASE}/ipo"

    def _fetch(self, item: dict):
        provider = _provider(self.URL, {"data": {"ipo": [item]}})
        return provider.fetch_events((CorporateActionType.IPO,))

    def test_price_precedence_ipo_price_final_wins_over_detail_price(self):
        item = {
            "company_symbol": "BBCA",
            "ipo_id": "i1",
            "ipo_price": {"minimum": 0, "maximum": 0, "final": 170},
            "ipo_data_detail": {"price": 999},
        }
        events = self._fetch(item)
        assert events[0].price == "170"

    def test_price_falls_back_to_detail_price_when_final_missing(self):
        item = {
            "company_symbol": "BBCA",
            "ipo_id": "i1",
            "ipo_price": {"minimum": 0, "maximum": 0},  # no "final"
            "ipo_data_detail": {"price": 999},
        }
        events = self._fetch(item)
        assert events[0].price == "999"

    def test_price_none_when_both_missing(self):
        item = {"company_symbol": "BBCA", "ipo_id": "i1"}
        events = self._fetch(item)
        assert events[0].price is None

    def test_price_none_when_ipo_price_not_a_dict(self):
        item = {
            "company_symbol": "BBCA",
            "ipo_id": "i1",
            "ipo_price": "not-a-dict",
            "ipo_data_detail": {"price": 999},
        }
        events = self._fetch(item)
        assert events[0].price == "999"

    def test_nested_ipo_data_detail_maps_four_date_roles_plus_top_level_listing(self):
        item = {
            "company_symbol": "BBCA",
            "ipo_id": "i1",
            "ipo_listing_date": "2026-07-10",
            "ipo_data_detail": {
                "offering_start": "2026-06-20",
                "offering_end": "2026-06-25",
                "allotment_date": "2026-06-28",
                "refund_date": "2026-06-29",
            },
        }
        events = self._fetch(item)
        ev = events[0]
        assert _roles(ev) == {
            CorporateActionDateRole.LISTING_DATE,
            CorporateActionDateRole.OFFERING_START,
            CorporateActionDateRole.OFFERING_END,
            CorporateActionDateRole.ALLOTMENT_DATE,
            CorporateActionDateRole.REFUND_DATE,
        }

    def test_ipo_data_detail_missing_still_parses_top_level_listing_date(self):
        item = {"company_symbol": "BBCA", "ipo_id": "i1", "ipo_listing_date": "2026-07-10"}
        events = self._fetch(item)
        assert _roles(events[0]) == {CorporateActionDateRole.LISTING_DATE}

    def test_ipo_data_detail_not_a_dict_is_treated_as_empty(self):
        item = {
            "company_symbol": "BBCA",
            "ipo_id": "i1",
            "ipo_listing_date": "2026-07-10",
            "ipo_data_detail": "not-a-dict",
        }
        events = self._fetch(item)
        assert _roles(events[0]) == {CorporateActionDateRole.LISTING_DATE}

    def test_company_name_is_captured(self):
        item = {"company_symbol": "BBCA", "ipo_id": "i1", "company_name": "New Listco"}
        events = self._fetch(item)
        assert events[0].company_name == "New Listco"
