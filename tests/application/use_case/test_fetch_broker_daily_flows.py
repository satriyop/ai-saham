"""
Tests for FetchBrokerDailyFlowsUseCase — incremental save logic.

Covers the three bugs fixed in the 2026-06-24 code review:
  - refresh=True must overwrite existing rows (not filter by before_max_date)
  - incremental >= filter must include new broker codes for the current max date
  - active_codes must count from the full provider response, not just new rows
"""

from datetime import date
from decimal import Decimal

from src.application.use_case.fetch_broker_daily_flows_use_case import (
    FetchBrokerDailyFlowsRequest,
    FetchBrokerDailyFlowsResponse,
    FetchBrokerDailyFlowsUseCase,
)
from src.domain.entities.broker_flow import BrokerDailyFlow

# ── helpers ──────────────────────────────────────────────────────────────────

_D1 = date(2026, 6, 18)
_D2 = date(2026, 6, 19)
_D3 = date(2026, 6, 20)  # max date already in DB


def _flow(d: date, broker_code: str = "AK") -> BrokerDailyFlow:
    return BrokerDailyFlow(
        ticker="BBCA",
        broker_code=broker_code,
        broker_name=broker_code,
        date=d,
        buy_lot=10,
        sell_lot=5,
        net_lot=5,
        buy_value=Decimal("1000"),
        sell_value=Decimal("500"),
        net_value=Decimal("500"),
        avg_buy_price=Decimal("100"),
        avg_sell_price=Decimal("100"),
        avg_price=Decimal("100"),
        buy_pct=0.1,
        sell_pct=0.05,
    )


class FakeProvider:
    """Returns a fixed list of BrokerDailyFlow rows."""

    provider_name = "fake"

    def __init__(self, flows: list[BrokerDailyFlow]) -> None:
        self._flows = flows
        self.saved: list[BrokerDailyFlow] = []

    def fetch_broker_daily_flows(self, ticker, broker_codes, days):
        return list(self._flows)


class FakeRepository:
    """In-memory broker repository stub."""

    def __init__(
        self,
        existing_range: tuple[date, date] | None = None,
    ) -> None:
        self._range = existing_range
        self.saved_calls: list[list[BrokerDailyFlow]] = []

    def get_broker_daily_flow_date_range(self, ticker, source):
        # Return the range after any save (updated lazily)
        if self.saved_calls:
            all_rows = [r for batch in self.saved_calls for r in batch]
            if all_rows:
                dates = [r.date for r in all_rows]
                return (min(dates), max(dates))
        return self._range

    def save_broker_daily_flows(self, flows: list[BrokerDailyFlow]) -> None:
        self.saved_calls.append(list(flows))


def _run(
    provider_flows: list[BrokerDailyFlow],
    existing_range: tuple[date, date] | None,
    refresh: bool = False,
    expected_latest: date | None = None,
) -> tuple[FakeRepository, FetchBrokerDailyFlowsResponse]:
    provider = FakeProvider(provider_flows)
    repo = FakeRepository(existing_range=existing_range)
    uc = FetchBrokerDailyFlowsUseCase(provider=provider, repository=repo)
    req = FetchBrokerDailyFlowsRequest(
        ticker="BBCA",
        refresh=refresh,
        expected_latest_date=expected_latest or date(2099, 1, 1),  # never cached
    )
    resp = uc.execute(req)
    return repo, resp


# ── Fix #6: refresh overwrites existing rows ─────────────────────────────────


class TestRefreshOverwritesExistingRows:
    def test_refresh_saves_all_rows_including_before_max_date(self):
        """refresh=True must bypass the date filter so corrected rows are upserted."""
        existing_rows = [_flow(_D1, "AK"), _flow(_D2, "AK"), _flow(_D3, "AK")]
        provider_flows = existing_rows  # provider returns all 3 (corrected values)
        repo, resp = _run(
            provider_flows,
            existing_range=(_D1, _D3),
            refresh=True,
        )
        # All 3 rows should be saved — not filtered out by before_max_date
        assert repo.saved_calls, "expected save to be called"
        saved = repo.saved_calls[0]
        assert len(saved) == 3

    def test_non_refresh_only_saves_from_max_date(self):
        """Non-refresh path must still filter (regression guard)."""
        provider_flows = [_flow(_D1, "AK"), _flow(_D2, "AK"), _flow(_D3, "AK")]
        repo, resp = _run(
            provider_flows,
            existing_range=(_D1, _D2),
            refresh=False,
        )
        # Only D2 (=before_max_date) and D3 should be saved (>= filter)
        assert repo.saved_calls
        saved_dates = {r.date for r in repo.saved_calls[0]}
        assert _D1 not in saved_dates  # D1 < D2 — filtered out
        assert _D2 in saved_dates  # D2 == before_max_date — now included (fix #7)
        assert _D3 in saved_dates


# ── Fix #7: inclusive >= filter for new broker codes on max date ──────────────


class TestInclusiveDateFilter:
    def test_new_broker_code_on_max_date_is_saved(self):
        """A new broker code for the already-stored max date must be included."""
        # DB has: D3/AK already stored; max date = D3
        # Provider returns: D3/AK (existing) + D3/YP (new)
        provider_flows = [_flow(_D3, "AK"), _flow(_D3, "YP")]
        repo, resp = _run(
            provider_flows,
            existing_range=(_D1, _D3),
            refresh=False,
        )
        assert repo.saved_calls, "should have saved new broker code"
        saved_codes = {r.broker_code for r in repo.saved_calls[0]}
        assert "YP" in saved_codes  # new code on max date must be included

    def test_rows_strictly_before_max_date_are_excluded(self):
        """Rows for dates strictly older than before_max_date are still filtered."""
        provider_flows = [_flow(_D1, "AK"), _flow(_D3, "AK")]
        repo, resp = _run(
            provider_flows,
            existing_range=(_D2, _D3),  # before_max_date = D3
            refresh=False,
        )
        if repo.saved_calls:
            saved_dates = {r.date for r in repo.saved_calls[0]}
            assert _D1 not in saved_dates  # D1 < D3 — older, filtered


# ── Fix #9: active_codes from full provider response ─────────────────────────


class TestActiveCodesFromFullProviderResponse:
    def test_active_codes_reflects_full_provider_batch(self):
        """active_codes must count unique broker codes in the full provider response."""
        # DB has D1–D3 already; provider returns same 3 days with 5 broker codes
        provider_flows = [
            _flow(_D1, "AK"),
            _flow(_D1, "YP"),
            _flow(_D2, "BK"),
            _flow(_D3, "ZP"),
            _flow(_D3, "MG"),
        ]
        _, resp = _run(
            provider_flows,
            existing_range=(_D1, _D2),
            refresh=False,
        )
        # 5 unique broker codes across the full provider response
        assert resp.active_codes == 5

    def test_active_codes_is_0_when_provider_returns_nothing(self):
        provider = FakeProvider([])
        repo = FakeRepository(existing_range=(_D1, _D3))
        uc = FetchBrokerDailyFlowsUseCase(provider=provider, repository=repo)
        req = FetchBrokerDailyFlowsRequest(
            ticker="BBCA",
            refresh=False,
            expected_latest_date=date(2099, 1, 1),
        )
        resp = uc.execute(req)
        assert resp.active_codes == 0

    def test_incremental_active_codes_not_undercounted(self):
        """After an incremental refresh adding 1 day, active_codes shows full window."""
        provider_flows = [
            _flow(_D1, "AK"),
            _flow(_D1, "YP"),  # 2 codes on D1
            _flow(_D2, "ZP"),  # 1 new code on D2 (new day)
        ]
        _, resp = _run(
            provider_flows,
            existing_range=(_D1, _D1),  # only D1 in DB
            refresh=False,
        )
        # Provider has 3 unique codes; active_codes must be 3, not 1
        assert resp.active_codes == 3
