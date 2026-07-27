"""Tests for FetchFinancialsUseCase freshness and orchestration policy."""

from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_case.fetch_financials_use_case import (
    FetchFinancialsRequest,
    FetchFinancialsUseCase,
)
from src.domain.ports.financials_provider import FinancialsProvider
from src.domain.ports.financials_repository import FinancialsRepository
from src.domain.value_objects.company_financial_period import (
    CompanyFinancialPeriod,
    FinancialPeriodType,
)


class _FakeProvider(FinancialsProvider):
    def __init__(self, periods_by_ticker: dict[str, list[CompanyFinancialPeriod]] | None = None):
        self.periods_by_ticker = periods_by_ticker or {}
        self.calls: list[str] = []

    def fetch_statements(
        self,
        ticker: str,
        *,
        include_quarterly: bool = True,
        include_annual: bool = True,
    ) -> list[CompanyFinancialPeriod]:
        self.calls.append(ticker)
        return list(self.periods_by_ticker.get(ticker, []))


class _FakeRepo(FinancialsRepository):
    def __init__(self) -> None:
        self.rows: list[CompanyFinancialPeriod] = []
        self._needs: dict[tuple[str, str], bool] = {}

    def upsert_many(self, periods: list[CompanyFinancialPeriod]) -> int:
        for p in periods:
            self.rows = [
                r
                for r in self.rows
                if not (
                    r.ticker == p.ticker
                    and r.period_end == p.period_end
                    and r.period_type == p.period_type
                    and r.source == p.source
                )
            ]
            self.rows.append(p)
        return len(periods)

    def list_for_ticker(
        self,
        ticker: str,
        *,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> list[CompanyFinancialPeriod]:
        out = [r for r in self.rows if r.ticker == ticker.upper()]
        if period_type is not None:
            out = [r for r in out if r.period_type == period_type]
        if source is not None:
            out = [r for r in out if r.source == source]
        return sorted(out, key=lambda r: r.period_end, reverse=True)

    def latest_period_end(
        self,
        ticker: str,
        *,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> date | None:
        rows = self.list_for_ticker(ticker, period_type=period_type, source=source)
        return rows[0].period_end if rows else None

    def needs_refresh(self, ticker: str, ttl_days: int, *, source: str) -> bool:
        return self._needs.get((ticker.upper(), source), True)


def _p(ticker: str, end: date) -> CompanyFinancialPeriod:
    return CompanyFinancialPeriod(
        ticker=ticker,
        period_end=end,
        period_type="quarter",
        source="yahoo",
        currency="IDR",
        total_revenue=1,
        net_income=2,
        net_income_incl_nci=2,
        interest_income=3,
        operating_income=None,
        eps_basic=1.0,
        eps_diluted=1.0,
        fetched_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
    )


def test_cached_skips_provider():
    provider = _FakeProvider({"BBCA": [_p("BBCA", date(2026, 3, 31))]})
    repo = _FakeRepo()
    repo.rows = [_p("BBCA", date(2026, 3, 31))]
    repo._needs[("BBCA", "yahoo")] = False

    uc = FetchFinancialsUseCase(provider, repo)
    response = uc.execute(FetchFinancialsRequest(tickers=("BBCA",)))

    assert provider.calls == []
    assert response.results[0].status == "cached"
    assert response.cached_count == 1


def test_force_refresh_fetches_and_stores():
    provider = _FakeProvider(
        {"BBCA": [_p("BBCA", date(2026, 3, 31)), _p("BBCA", date(2025, 12, 31))]}
    )
    repo = _FakeRepo()
    repo._needs[("BBCA", "yahoo")] = False

    uc = FetchFinancialsUseCase(provider, repo)
    response = uc.execute(FetchFinancialsRequest(tickers=("BBCA",), force_refresh=True))

    assert provider.calls == ["BBCA"]
    assert response.results[0].status == "fetched"
    assert response.results[0].periods_stored == 2
    assert response.results[0].latest_period_end == date(2026, 3, 31)
    assert len(repo.rows) == 2


def test_empty_provider_result():
    provider = _FakeProvider({"BBCA": []})
    repo = _FakeRepo()
    uc = FetchFinancialsUseCase(provider, repo)

    response = uc.execute(FetchFinancialsRequest(tickers=("BBCA",), force_refresh=True))

    assert response.results[0].status == "empty"
    assert response.results[0].error is not None


def test_provider_exception_maps_to_error():
    class _Boom(_FakeProvider):
        def fetch_statements(self, ticker, *, include_quarterly=True, include_annual=True):
            raise RuntimeError("network down")

    uc = FetchFinancialsUseCase(_Boom(), _FakeRepo())
    response = uc.execute(FetchFinancialsRequest(tickers=("BBCA",), force_refresh=True))

    assert response.results[0].status == "error"
    assert "network down" in (response.results[0].error or "")
