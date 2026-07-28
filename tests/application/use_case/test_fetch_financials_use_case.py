"""Tests for FetchFinancialsUseCase multi-kind freshness and orchestration."""

from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_case.fetch_financials_use_case import (
    FetchFinancialsRequest,
    FetchFinancialsUseCase,
)
from src.domain.ports.financials_provider import FinancialsProvider
from src.domain.ports.financials_repository import FinancialsRepository
from src.domain.value_objects.company_financial_period import (
    ALL_STATEMENT_KINDS,
    CompanyFinancialPeriod,
    FinancialPeriodType,
    FinancialStatementKind,
)


class _FakeProvider(FinancialsProvider):
    def __init__(self, periods_by_ticker: dict[str, list[CompanyFinancialPeriod]] | None = None):
        self.periods_by_ticker = periods_by_ticker or {}
        self.calls: list[tuple[str, frozenset[str]]] = []

    def fetch_statements(
        self,
        ticker: str,
        *,
        include_quarterly: bool = True,
        include_annual: bool = True,
        statement_kinds: frozenset[FinancialStatementKind],
    ) -> list[CompanyFinancialPeriod]:
        self.calls.append((ticker, frozenset(statement_kinds)))
        return [
            p for p in self.periods_by_ticker.get(ticker, []) if p.statement_kind in statement_kinds
        ]


class _FakeRepo(FinancialsRepository):
    def __init__(self) -> None:
        self.rows: list[CompanyFinancialPeriod] = []
        self._needs: dict[tuple[str, str, str], bool] = {}

    def upsert_many(self, periods: list[CompanyFinancialPeriod]) -> int:
        for p in periods:
            self.rows = [
                r
                for r in self.rows
                if not (
                    r.ticker == p.ticker
                    and r.statement_kind == p.statement_kind
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
        statement_kind: FinancialStatementKind | None = None,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> list[CompanyFinancialPeriod]:
        out = [r for r in self.rows if r.ticker == ticker.upper()]
        if statement_kind is not None:
            out = [r for r in out if r.statement_kind == statement_kind]
        if period_type is not None:
            out = [r for r in out if r.period_type == period_type]
        if source is not None:
            out = [r for r in out if r.source == source]
        return sorted(out, key=lambda r: r.period_end, reverse=True)

    def latest_period_end(
        self,
        ticker: str,
        *,
        statement_kind: FinancialStatementKind | None = None,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> date | None:
        rows = self.list_for_ticker(
            ticker,
            statement_kind=statement_kind,
            period_type=period_type,
            source=source,
        )
        return rows[0].period_end if rows else None

    def needs_refresh(
        self,
        ticker: str,
        ttl_days: int,
        *,
        source: str,
        statement_kind: FinancialStatementKind,
    ) -> bool:
        return self._needs.get((ticker.upper(), source, statement_kind), True)


def _p(
    ticker: str,
    end: date,
    *,
    kind: FinancialStatementKind = "income",
) -> CompanyFinancialPeriod:
    return CompanyFinancialPeriod(
        ticker=ticker,
        period_end=end,
        period_type="quarter",
        statement_kind=kind,
        source="yahoo",
        currency="IDR",
        total_revenue=1 if kind == "income" else None,
        net_income=2 if kind == "income" else None,
        net_income_incl_nci=2 if kind == "income" else None,
        interest_income=3 if kind == "income" else None,
        operating_income=None,
        eps_basic=1.0 if kind == "income" else None,
        eps_diluted=1.0 if kind == "income" else None,
        total_assets=10 if kind == "balance" else None,
        total_liabilities=None,
        stockholders_equity=None,
        cash_and_equivalents=None,
        total_debt=None,
        operating_cash_flow=20 if kind == "cashflow" else None,
        investing_cash_flow=None,
        financing_cash_flow=None,
        free_cash_flow=None,
        capital_expenditure=None,
        end_cash_position=None,
        fetched_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
    )


def test_cached_skips_provider_when_all_kinds_fresh():
    provider = _FakeProvider({"BBCA": [_p("BBCA", date(2026, 3, 31))]})
    repo = _FakeRepo()
    repo.rows = [
        _p("BBCA", date(2026, 3, 31), kind="income"),
        _p("BBCA", date(2026, 3, 31), kind="balance"),
        _p("BBCA", date(2026, 3, 31), kind="cashflow"),
    ]
    for kind in ALL_STATEMENT_KINDS:
        repo._needs[("BBCA", "yahoo", kind)] = False

    uc = FetchFinancialsUseCase(provider, repo)
    response = uc.execute(FetchFinancialsRequest(tickers=("BBCA",)))

    assert provider.calls == []
    assert response.results[0].status == "cached"


def test_missing_balance_fetches_only_balance_kind():
    provider = _FakeProvider(
        {
            "BBCA": [
                _p("BBCA", date(2026, 3, 31), kind="income"),
                _p("BBCA", date(2026, 3, 31), kind="balance"),
            ]
        }
    )
    repo = _FakeRepo()
    repo._needs[("BBCA", "yahoo", "income")] = False
    repo._needs[("BBCA", "yahoo", "balance")] = True
    repo._needs[("BBCA", "yahoo", "cashflow")] = False

    uc = FetchFinancialsUseCase(provider, repo)
    response = uc.execute(
        FetchFinancialsRequest(
            tickers=("BBCA",),
            statement_kinds=frozenset({"income", "balance", "cashflow"}),
        )
    )

    assert len(provider.calls) == 1
    assert provider.calls[0][1] == frozenset({"balance"})
    assert response.results[0].status == "fetched"
    assert response.results[0].kinds_fetched == ("balance",)


def test_force_refresh_fetches_and_stores():
    provider = _FakeProvider(
        {
            "BBCA": [
                _p("BBCA", date(2026, 3, 31)),
                _p("BBCA", date(2025, 12, 31)),
            ]
        }
    )
    repo = _FakeRepo()
    for kind in ALL_STATEMENT_KINDS:
        repo._needs[("BBCA", "yahoo", kind)] = False

    uc = FetchFinancialsUseCase(provider, repo)
    response = uc.execute(
        FetchFinancialsRequest(
            tickers=("BBCA",),
            force_refresh=True,
            statement_kinds=frozenset({"income"}),
        )
    )

    assert provider.calls == [("BBCA", frozenset({"income"}))]
    assert response.results[0].status == "fetched"
    assert response.results[0].periods_stored == 2
    assert response.results[0].latest_period_end == date(2026, 3, 31)


def test_empty_provider_result():
    provider = _FakeProvider({"BBCA": []})
    repo = _FakeRepo()
    uc = FetchFinancialsUseCase(provider, repo)

    response = uc.execute(
        FetchFinancialsRequest(
            tickers=("BBCA",),
            force_refresh=True,
            statement_kinds=frozenset({"income"}),
        )
    )

    assert response.results[0].status == "empty"
    assert response.results[0].error is not None


def test_provider_exception_maps_to_error():
    class _Boom(_FakeProvider):
        def fetch_statements(
            self,
            ticker,
            *,
            include_quarterly=True,
            include_annual=True,
            statement_kinds=frozenset(),
        ):
            raise RuntimeError("network down")

    uc = FetchFinancialsUseCase(_Boom(), _FakeRepo())
    response = uc.execute(
        FetchFinancialsRequest(
            tickers=("BBCA",),
            force_refresh=True,
            statement_kinds=frozenset({"income"}),
        )
    )

    assert response.results[0].status == "error"
    assert "network down" in (response.results[0].error or "")


def test_partial_kinds_still_fetched_status():
    """Provider returns only income while all kinds requested → fetched not error."""
    provider = _FakeProvider({"BBCA": [_p("BBCA", date(2026, 3, 31), kind="income")]})
    repo = _FakeRepo()
    uc = FetchFinancialsUseCase(provider, repo)

    response = uc.execute(FetchFinancialsRequest(tickers=("BBCA",), force_refresh=True))

    assert response.results[0].status == "fetched"
    assert response.results[0].kinds_fetched == ("income",)
