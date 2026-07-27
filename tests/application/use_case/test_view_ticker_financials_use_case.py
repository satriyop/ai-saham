"""Unit tests for ViewTickerFinancialsUseCase."""

from __future__ import annotations

from datetime import date, datetime, timezone

from src.application.use_case.view_ticker_financials_use_case import (
    ViewTickerFinancialsRequest,
    ViewTickerFinancialsUseCase,
)
from src.domain.ports.financials_repository import FinancialsRepository
from src.domain.value_objects.company_financial_period import (
    CompanyFinancialPeriod,
    FinancialPeriodType,
)


class _FakeRepo(FinancialsRepository):
    def __init__(self, rows: list[CompanyFinancialPeriod] | None = None) -> None:
        self.rows = list(rows or [])

    def upsert_many(self, periods: list[CompanyFinancialPeriod]) -> int:
        self.rows.extend(periods)
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
        return True


def _p(end: date, *, period_type: str = "quarter") -> CompanyFinancialPeriod:
    return CompanyFinancialPeriod(
        ticker="BBCA",
        period_end=end,
        period_type=period_type,  # type: ignore[arg-type]
        source="yahoo",
        currency="IDR",
        total_revenue=1,
        net_income=2,
        net_income_incl_nci=3,
        interest_income=4,
        operating_income=None,
        eps_basic=1.0,
        eps_diluted=1.0,
        fetched_at=datetime(2026, 7, 28, tzinfo=timezone.utc),
    )


def test_income_returns_limited_newest_first():
    repo = _FakeRepo(
        [
            _p(date(2025, 3, 31)),
            _p(date(2026, 3, 31)),
            _p(date(2025, 12, 31)),
            _p(date(2025, 12, 31), period_type="annual"),
        ]
    )
    result = ViewTickerFinancialsUseCase(repo).execute(
        ViewTickerFinancialsRequest(ticker="bbca", limit=2)
    )

    assert result.status == "ok"
    assert result.statement == "income"
    assert [p.period_end for p in result.periods] == [
        date(2026, 3, 31),
        date(2025, 12, 31),
    ]
    assert result.as_of == date(2026, 3, 31)
    assert result.source == "yahoo"
    assert result.fetch_hint == "saham fetch financials BBCA"


def test_empty_income_cache():
    result = ViewTickerFinancialsUseCase(_FakeRepo()).execute(
        ViewTickerFinancialsRequest(ticker="BBCA")
    )
    assert result.status == "empty"
    assert result.periods == ()
    assert "fetch financials" in (result.message or "")


def test_balance_unsupported():
    repo = _FakeRepo([_p(date(2026, 3, 31))])
    result = ViewTickerFinancialsUseCase(repo).execute(
        ViewTickerFinancialsRequest(ticker="BBCA", statement="balance")
    )
    assert result.status == "unsupported"
    assert result.periods == ()
    assert "not cached yet" in (result.message or "")


def test_annual_filter():
    repo = _FakeRepo(
        [
            _p(date(2025, 12, 31), period_type="annual"),
            _p(date(2026, 3, 31), period_type="quarter"),
        ]
    )
    result = ViewTickerFinancialsUseCase(repo).execute(
        ViewTickerFinancialsRequest(ticker="BBCA", period_type="annual")
    )
    assert result.status == "ok"
    assert len(result.periods) == 1
    assert result.periods[0].period_type == "annual"
