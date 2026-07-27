"""Tests for SQLiteCompanyFinancialsRepository."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src.domain.value_objects.company_financial_period import CompanyFinancialPeriod
from src.infrastructure.persistence.sqlite_company_financials_repository import (
    SQLiteCompanyFinancialsRepository,
)


def _period(
    ticker: str = "BBCA",
    period_end: date = date(2026, 3, 31),
    period_type: str = "quarter",
    source: str = "yahoo",
    net_income: int | None = 14_689_799_000_000,
    fetched_at: datetime | None = None,
) -> CompanyFinancialPeriod:
    return CompanyFinancialPeriod(
        ticker=ticker,
        period_end=period_end,
        period_type=period_type,  # type: ignore[arg-type]
        source=source,
        currency="IDR",
        total_revenue=28_660_037_000_000,
        net_income=net_income,
        net_income_incl_nci=net_income,
        interest_income=24_387_580_000_000,
        operating_income=None,
        eps_basic=119.0,
        eps_diluted=119.0,
        fetched_at=fetched_at or datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
    )


def test_upsert_and_list_newest_first(tmp_path):
    repo = SQLiteCompanyFinancialsRepository(tmp_path / "data.db")
    repo.upsert_many(
        [
            _period(period_end=date(2025, 12, 31), net_income=1),
            _period(period_end=date(2026, 3, 31), net_income=2),
        ]
    )

    rows = repo.list_for_ticker("bbca", period_type="quarter", source="yahoo")

    assert [r.period_end for r in rows] == [date(2026, 3, 31), date(2025, 12, 31)]
    assert rows[0].net_income == 2
    assert rows[0].source == "yahoo"


def test_upsert_replaces_same_pk(tmp_path):
    repo = SQLiteCompanyFinancialsRepository(tmp_path / "data.db")
    repo.upsert_many([_period(net_income=100)])
    repo.upsert_many([_period(net_income=200)])

    rows = repo.list_for_ticker("BBCA")
    assert len(rows) == 1
    assert rows[0].net_income == 200


def test_latest_period_end(tmp_path):
    repo = SQLiteCompanyFinancialsRepository(tmp_path / "data.db")
    repo.upsert_many(
        [
            _period(period_end=date(2025, 6, 30)),
            _period(period_end=date(2026, 3, 31)),
            _period(period_end=date(2025, 12, 31), period_type="annual"),
        ]
    )

    assert repo.latest_period_end("BBCA") == date(2026, 3, 31)
    assert repo.latest_period_end("BBCA", period_type="annual") == date(2025, 12, 31)
    assert repo.latest_period_end("ZZZZ") is None


def test_needs_refresh_missing_and_ttl(tmp_path, monkeypatch):
    class _DateProxy:
        @staticmethod
        def today():
            return date(2026, 7, 28)

        @staticmethod
        def fromisoformat(value: str):
            return date.fromisoformat(value)

    monkeypatch.setattr(
        "src.infrastructure.persistence.sqlite_company_financials_repository.date",
        _DateProxy,
    )

    repo = SQLiteCompanyFinancialsRepository(tmp_path / "data.db")
    assert repo.needs_refresh("BBCA", ttl_days=7, source="yahoo") is True

    repo.upsert_many(
        [
            _period(
                fetched_at=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
            )
        ]
    )
    assert repo.needs_refresh("BBCA", ttl_days=7, source="yahoo") is False

    stale_repo = SQLiteCompanyFinancialsRepository(tmp_path / "stale.db")
    stale_repo.upsert_many(
        [
            _period(
                fetched_at=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc) - timedelta(days=10),
            )
        ]
    )
    assert stale_repo.needs_refresh("BBCA", ttl_days=7, source="yahoo") is True
