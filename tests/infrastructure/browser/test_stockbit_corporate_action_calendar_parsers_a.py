"""
Per-type parser tests (batch A): dividend, stock_split, reverse_split,
rights_issue, bonus.

Fixtures mirror docs/stockbit_api_data.md section 21 exact key names/shapes.
See test_stockbit_corporate_action_calendar.py for cross-cutting guards
(company_symbol drop, ticker uppercasing, company_id int-zero, date parsing)
that apply identically to every type — not re-verified here except where a
type has a genuinely distinct trap (e.g. bonus's copy-pasted stocksplit_* keys).
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


# ── dividend ─────────────────────────────────────────────────────────────────


class TestDividendParser:
    URL = f"{BASE}/dividend"

    def _fetch(self, item: dict):
        provider = _provider(self.URL, {"data": {"dividend": [item]}})
        return provider.fetch_events((CorporateActionType.DIVIDEND,))

    def test_full_row_maps_all_four_date_roles(self):
        item = {
            "company_symbol": "BBCA",
            "company_id": 1,
            "dividend_id": "d1",
            "corp_action_active": True,
            "dividend_cumdate": "2026-07-08",
            "dividend_exdate": "2026-07-09",
            "dividend_recdate": "2026-07-10",
            "dividend_paydate": "2026-07-31",
            "dividend_value": "25.65",
            "dividend_currency": "CURRENCY_IDR",
        }
        events = self._fetch(item)
        assert len(events) == 1
        ev = events[0]
        assert ev.event_type == CorporateActionType.DIVIDEND
        assert ev.source_event_id == "d1"
        assert _roles(ev) == {
            CorporateActionDateRole.CUM_DATE,
            CorporateActionDateRole.EX_DATE,
            CorporateActionDateRole.RECORDING_DATE,
            CorporateActionDateRole.PAYMENT_DATE,
        }
        assert ev.amount_value == "25.65"
        assert ev.amount_currency == "CURRENCY_IDR"

    def test_dividend_value_truthy_only(self):
        """dividend_value of "0" or 0 is falsy → amount_value stays None."""
        item = {"company_symbol": "BBCA", "dividend_id": "d1", "dividend_value": 0}
        events = self._fetch(item)
        assert events[0].amount_value is None

    def test_dividend_value_missing_is_none(self):
        item = {"company_symbol": "BBCA", "dividend_id": "d1"}
        events = self._fetch(item)
        assert events[0].amount_value is None

    def test_dividend_currency_missing_is_none(self):
        item = {"company_symbol": "BBCA", "dividend_id": "d1", "dividend_value": "25.65"}
        events = self._fetch(item)
        assert events[0].amount_currency is None


# ── stock_split ──────────────────────────────────────────────────────────────


class TestStockSplitParser:
    URL = f"{BASE}/stocksplit"

    def _fetch(self, item: dict):
        provider = _provider(self.URL, {"data": {"stocksplit": [item]}})
        return provider.fetch_events((CorporateActionType.STOCK_SPLIT,))

    def test_full_row_maps_three_date_roles_and_ratios(self):
        item = {
            "company_symbol": "BBCA",
            "stocksplit_id": "s1",
            "stocksplit_cumdate": "2026-07-28",
            "stocksplit_exdate": "2026-07-29",
            "stocksplit_recdate": "2026-07-30",
            "stocksplit_old": "1",
            "stocksplit_new": "25",
        }
        events = self._fetch(item)
        ev = events[0]
        assert _roles(ev) == {
            CorporateActionDateRole.CUM_DATE,
            CorporateActionDateRole.EX_DATE,
            CorporateActionDateRole.RECORDING_DATE,
        }
        assert ev.ratio_old == "1"
        assert ev.ratio_new == "25"

    def test_no_payment_date_role(self):
        item = {
            "company_symbol": "BBCA",
            "stocksplit_id": "s1",
            "stocksplit_paymentdate": "2026-08-01",  # not a real field for this type
        }
        events = self._fetch(item)
        assert CorporateActionDateRole.PAYMENT_DATE not in _roles(events[0])

    def test_ratio_old_zero_is_none(self):
        item = {"company_symbol": "BBCA", "stocksplit_id": "s1", "stocksplit_old": 0}
        events = self._fetch(item)
        assert events[0].ratio_old is None


# ── reverse_split ────────────────────────────────────────────────────────────


class TestReverseSplitParser:
    URL = f"{BASE}/reversesplit"

    def test_list_key_is_stock_reverse_not_reversesplit(self):
        item = {
            "company_symbol": "BBCA",
            "stock_reverse_id": "r1",
            "stock_reverse_cumdate": "2026-07-08",
            "stock_reverse_exdate": "2026-07-09",
            "stock_reverse_recdate": "2026-07-10",
            "stock_reverse_old": "10",
            "stock_reverse_new": "1",
        }
        # Wrong key ("reversesplit") must yield nothing.
        wrong = _provider(self.URL, {"data": {"reversesplit": [item]}})
        assert wrong.fetch_events((CorporateActionType.REVERSE_SPLIT,)) == []

        # Correct key ("stock_reverse") parses.
        right = _provider(self.URL, {"data": {"stock_reverse": [item]}})
        events = right.fetch_events((CorporateActionType.REVERSE_SPLIT,))
        assert len(events) == 1
        ev = events[0]
        assert ev.source_event_id == "r1"
        assert ev.ratio_old == "10"
        assert ev.ratio_new == "1"
        assert _roles(ev) == {
            CorporateActionDateRole.CUM_DATE,
            CorporateActionDateRole.EX_DATE,
            CorporateActionDateRole.RECORDING_DATE,
        }

    def test_empty_list_yields_empty(self):
        provider = _provider(self.URL, {"data": {"stock_reverse": []}})
        assert provider.fetch_events((CorporateActionType.REVERSE_SPLIT,)) == []


# ── rights_issue ─────────────────────────────────────────────────────────────


class TestRightsIssueParser:
    URL = f"{BASE}/rightissue"

    def _fetch(self, item: dict):
        provider = _provider(self.URL, {"data": {"rightissue": [item]}})
        return provider.fetch_events((CorporateActionType.RIGHTS_ISSUE,))

    def test_full_row_maps_six_date_roles(self):
        item = {
            "company_symbol": "BBCA",
            "rightissue_id": "ri1",
            "rightissue_cumdate": "2026-08-24",
            "rightissue_exdate": "2026-08-26",
            "rightissue_recdate": "2026-08-27",
            "rightissue_subdate": "2026-08-28",
            "rightissue_trading_start": "2026-08-31",
            "rightissue_trading_end": "2026-09-04",
            "rightissue_old": "2",
            "rightissue_new": "1",
            "rightissue_price": 500,
        }
        events = self._fetch(item)
        ev = events[0]
        assert _roles(ev) == {
            CorporateActionDateRole.CUM_DATE,
            CorporateActionDateRole.EX_DATE,
            CorporateActionDateRole.RECORDING_DATE,
            CorporateActionDateRole.SUBSCRIPTION_DATE,
            CorporateActionDateRole.TRADING_START,
            CorporateActionDateRole.TRADING_END,
        }
        assert ev.price == "500"  # int 500 -> string "500"

    def test_empty_subscription_date_is_dropped_while_siblings_remain(self):
        """rightissue_subdate is often "" in real data — must be dropped
        while cum/ex/rec/trading_start/trading_end still parse."""
        item = {
            "company_symbol": "BBCA",
            "rightissue_id": "ri1",
            "rightissue_cumdate": "2026-08-24",
            "rightissue_exdate": "2026-08-26",
            "rightissue_subdate": "",
        }
        events = self._fetch(item)
        roles = _roles(events[0])
        assert CorporateActionDateRole.SUBSCRIPTION_DATE not in roles
        assert CorporateActionDateRole.CUM_DATE in roles
        assert CorporateActionDateRole.EX_DATE in roles

    def test_price_int_confirmed_as_string(self):
        item = {"company_symbol": "BBCA", "rightissue_id": "ri1", "rightissue_price": 500}
        events = self._fetch(item)
        assert events[0].price == "500"
        assert isinstance(events[0].price, str)

    def test_empty_price_is_none(self):
        item = {"company_symbol": "BBCA", "rightissue_id": "ri1", "rightissue_price": ""}
        events = self._fetch(item)
        assert events[0].price is None

    def test_missing_price_is_none(self):
        item = {"company_symbol": "BBCA", "rightissue_id": "ri1"}
        events = self._fetch(item)
        assert events[0].price is None

    def test_price_zero_is_not_none(self):
        """price uses `not in (None, "")` guard, not truthiness — 0 is valid."""
        item = {"company_symbol": "BBCA", "rightissue_id": "ri1", "rightissue_price": 0}
        events = self._fetch(item)
        assert events[0].price == "0"


# ── bonus (HIGH RISK: reuses stocksplit_* field names — copy-paste trap) ────


class TestBonusParser:
    URL = f"{BASE}/bonus"

    def _fetch(self, item: dict):
        provider = _provider(self.URL, {"data": {"bonus": [item]}})
        return provider.fetch_events((CorporateActionType.BONUS,))

    def test_source_id_is_sahabonus_id_not_bonus_id(self):
        item = {
            "company_symbol": "BBCA",
            "sahabonus_id": "sb1",
            "bonus_id": "wrong-should-be-ignored",
        }
        events = self._fetch(item)
        assert events[0].source_event_id == "sb1"

    def test_dates_reuse_stocksplit_field_names_including_paymentdate(self):
        """This is the documented copy-paste-bug-prone mapping: bonus dates
        come from stocksplit_cumdate/exdate/recdate/paymentdate, NOT any
        bonus_*-prefixed fields."""
        item = {
            "company_symbol": "BBCA",
            "sahabonus_id": "sb1",
            "stocksplit_cumdate": "2026-07-08",
            "stocksplit_exdate": "2026-07-09",
            "stocksplit_recdate": "2026-07-10",
            "stocksplit_paymentdate": "2026-07-30",
        }
        events = self._fetch(item)
        ev = events[0]
        assert _roles(ev) == {
            CorporateActionDateRole.CUM_DATE,
            CorporateActionDateRole.EX_DATE,
            CorporateActionDateRole.RECORDING_DATE,
            CorporateActionDateRole.PAYMENT_DATE,
        }
        payment_row = next(
            d for d in ev.dates if d.date_role == CorporateActionDateRole.PAYMENT_DATE
        )
        assert payment_row.event_date.isoformat() == "2026-07-30"

    def test_ratios_reuse_stocksplit_old_new_fields(self):
        item = {
            "company_symbol": "BBCA",
            "sahabonus_id": "sb1",
            "stocksplit_old": "100",
            "stocksplit_new": "30",
        }
        events = self._fetch(item)
        assert events[0].ratio_old == "100"
        assert events[0].ratio_new == "30"

    def test_event_type_is_bonus_not_stock_split(self):
        item = {"company_symbol": "BBCA", "sahabonus_id": "sb1"}
        events = self._fetch(item)
        assert events[0].event_type == CorporateActionType.BONUS
