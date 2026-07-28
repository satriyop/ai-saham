"""Tests for SQLiteCompanyFinancialsRepository (multi-kind schema)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone

from src.domain.value_objects.company_financial_period import CompanyFinancialPeriod
from src.infrastructure.persistence.sqlite_company_financials_repository import (
    SQLiteCompanyFinancialsRepository,
)


def _period(
    ticker: str = "BBCA",
    period_end: date = date(2026, 3, 31),
    period_type: str = "quarter",
    statement_kind: str = "income",
    source: str = "yahoo",
    net_income: int | None = 14_689_799_000_000,
    total_assets: int | None = None,
    operating_cash_flow: int | None = None,
    fetched_at: datetime | None = None,
) -> CompanyFinancialPeriod:
    return CompanyFinancialPeriod(
        ticker=ticker,
        period_end=period_end,
        period_type=period_type,  # type: ignore[arg-type]
        statement_kind=statement_kind,  # type: ignore[arg-type]
        source=source,
        currency="IDR",
        total_revenue=28_660_037_000_000 if statement_kind == "income" else None,
        net_income=net_income if statement_kind == "income" else None,
        net_income_incl_nci=net_income if statement_kind == "income" else None,
        interest_income=24_387_580_000_000 if statement_kind == "income" else None,
        operating_income=None,
        eps_basic=119.0 if statement_kind == "income" else None,
        eps_diluted=119.0 if statement_kind == "income" else None,
        total_assets=total_assets,
        total_liabilities=None,
        stockholders_equity=None,
        cash_and_equivalents=None,
        total_debt=None,
        operating_cash_flow=operating_cash_flow,
        investing_cash_flow=None,
        financing_cash_flow=None,
        free_cash_flow=None,
        capital_expenditure=None,
        end_cash_position=None,
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

    rows = repo.list_for_ticker(
        "bbca", statement_kind="income", period_type="quarter", source="yahoo"
    )

    assert [r.period_end for r in rows] == [date(2026, 3, 31), date(2025, 12, 31)]
    assert rows[0].net_income == 2
    assert rows[0].statement_kind == "income"


def test_same_period_two_kinds_are_separate_rows(tmp_path):
    repo = SQLiteCompanyFinancialsRepository(tmp_path / "data.db")
    end = date(2026, 3, 31)
    repo.upsert_many(
        [
            _period(period_end=end, statement_kind="income", net_income=100),
            _period(
                period_end=end,
                statement_kind="balance",
                net_income=None,
                total_assets=999,
            ),
        ]
    )

    all_rows = repo.list_for_ticker("BBCA", source="yahoo")
    assert len(all_rows) == 2
    income = repo.list_for_ticker("BBCA", statement_kind="income")
    balance = repo.list_for_ticker("BBCA", statement_kind="balance")
    assert len(income) == 1 and income[0].net_income == 100
    assert len(balance) == 1 and balance[0].total_assets == 999


def test_upsert_replaces_same_pk(tmp_path):
    repo = SQLiteCompanyFinancialsRepository(tmp_path / "data.db")
    repo.upsert_many([_period(net_income=100)])
    repo.upsert_many([_period(net_income=200)])

    rows = repo.list_for_ticker("BBCA", statement_kind="income")
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

    assert repo.latest_period_end("BBCA", statement_kind="income") == date(2026, 3, 31)
    assert repo.latest_period_end("BBCA", statement_kind="income", period_type="annual") == date(
        2025, 12, 31
    )
    assert repo.latest_period_end("ZZZZ") is None


def test_needs_refresh_is_per_kind(tmp_path, monkeypatch):
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
    repo.upsert_many(
        [
            _period(
                statement_kind="income",
                fetched_at=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
            )
        ]
    )
    assert repo.needs_refresh("BBCA", ttl_days=7, source="yahoo", statement_kind="income") is False
    # Balance missing → must refresh even though income is fresh
    assert repo.needs_refresh("BBCA", ttl_days=7, source="yahoo", statement_kind="balance") is True

    stale_repo = SQLiteCompanyFinancialsRepository(tmp_path / "stale.db")
    stale_repo.upsert_many(
        [
            _period(
                fetched_at=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc) - timedelta(days=10),
            )
        ]
    )
    assert (
        stale_repo.needs_refresh("BBCA", ttl_days=7, source="yahoo", statement_kind="income")
        is True
    )


def test_migrates_legacy_income_only_schema(tmp_path):
    """Old PK without statement_kind survives as income rows."""
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE company_financials (
            ticker TEXT NOT NULL,
            period_end TEXT NOT NULL,
            period_type TEXT NOT NULL,
            source TEXT NOT NULL,
            currency TEXT,
            total_revenue INTEGER,
            net_income INTEGER,
            net_income_incl_nci INTEGER,
            interest_income INTEGER,
            operating_income INTEGER,
            eps_basic REAL,
            eps_diluted REAL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (ticker, period_end, period_type, source)
        );
        CREATE TABLE _schema_migrations (
            namespace TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (namespace, version)
        );
        INSERT INTO _schema_migrations(namespace, version) VALUES
            ('company_financials', 0),
            ('company_financials', 1),
            ('company_financials', 2);
        INSERT INTO company_financials VALUES (
            'BBCA', '2026-03-31', 'quarter', 'yahoo', 'IDR',
            1, 2, 3, 4, NULL, 1.0, 1.0, '2026-07-28T00:00:00+00:00'
        );
        """
    )
    conn.commit()
    conn.close()

    repo = SQLiteCompanyFinancialsRepository(db)
    rows = repo.list_for_ticker("BBCA", statement_kind="income")
    assert len(rows) == 1
    assert rows[0].net_income == 2
    assert rows[0].statement_kind == "income"

    # Balance insert coexists
    repo.upsert_many(
        [
            _period(
                statement_kind="balance",
                net_income=None,
                total_assets=555,
            )
        ]
    )
    assert len(repo.list_for_ticker("BBCA")) == 2
