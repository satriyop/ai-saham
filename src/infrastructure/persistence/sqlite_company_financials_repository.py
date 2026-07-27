"""
SQLite implementation of FinancialsRepository.

Table: company_financials — multi-period income-statement line items.
Distinct from company_fundamentals (Stockbit keystats ratios).

Layer: Infrastructure
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path

from src.domain.ports.financials_repository import FinancialsRepository
from src.domain.value_objects.company_financial_period import (
    CompanyFinancialPeriod,
    FinancialPeriodType,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

_NAMESPACE = "company_financials"

_MIGRATIONS: list[tuple[int, str]] = [
    (
        0,
        """
        CREATE TABLE IF NOT EXISTS company_financials (
            ticker              TEXT NOT NULL,
            period_end          TEXT NOT NULL,
            period_type         TEXT NOT NULL,
            source              TEXT NOT NULL,
            currency            TEXT,
            total_revenue       INTEGER,
            net_income          INTEGER,
            net_income_incl_nci INTEGER,
            interest_income     INTEGER,
            operating_income    INTEGER,
            eps_basic           REAL,
            eps_diluted         REAL,
            fetched_at          TEXT NOT NULL,
            PRIMARY KEY (ticker, period_end, period_type, source)
        )
        """,
    ),
    (
        1,
        """
        CREATE INDEX IF NOT EXISTS idx_company_financials_ticker_period
            ON company_financials (ticker, period_type, period_end DESC)
        """,
    ),
    (
        2,
        """
        CREATE INDEX IF NOT EXISTS idx_company_financials_source_fetched
            ON company_financials (source, fetched_at)
        """,
    ),
]


class SQLiteCompanyFinancialsRepository(FinancialsRepository):
    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        SqliteMigrationRunner(self._db_path).run(_NAMESPACE, _MIGRATIONS)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_many(self, periods: list[CompanyFinancialPeriod]) -> int:
        if not periods:
            return 0
        sql = """
            INSERT INTO company_financials (
                ticker, period_end, period_type, source, currency,
                total_revenue, net_income, net_income_incl_nci,
                interest_income, operating_income, eps_basic, eps_diluted,
                fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker, period_end, period_type, source) DO UPDATE SET
                currency = excluded.currency,
                total_revenue = excluded.total_revenue,
                net_income = excluded.net_income,
                net_income_incl_nci = excluded.net_income_incl_nci,
                interest_income = excluded.interest_income,
                operating_income = excluded.operating_income,
                eps_basic = excluded.eps_basic,
                eps_diluted = excluded.eps_diluted,
                fetched_at = excluded.fetched_at
        """
        rows = [
            (
                p.ticker.upper(),
                p.period_end.isoformat(),
                p.period_type,
                p.source,
                p.currency,
                p.total_revenue,
                p.net_income,
                p.net_income_incl_nci,
                p.interest_income,
                p.operating_income,
                p.eps_basic,
                p.eps_diluted,
                p.fetched_at.isoformat(),
            )
            for p in periods
        ]
        with self._connect() as conn:
            conn.executemany(sql, rows)
        return len(rows)

    def list_for_ticker(
        self,
        ticker: str,
        *,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> list[CompanyFinancialPeriod]:
        clauses = ["ticker = ?"]
        params: list[str] = [ticker.upper()]
        if period_type is not None:
            clauses.append("period_type = ?")
            params.append(period_type)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM company_financials
                WHERE {where}
                ORDER BY period_end DESC, period_type ASC
                """,
                params,
            ).fetchall()
        return [self._row_to_period(row) for row in rows]

    def latest_period_end(
        self,
        ticker: str,
        *,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> date | None:
        clauses = ["ticker = ?"]
        params: list[str] = [ticker.upper()]
        if period_type is not None:
            clauses.append("period_type = ?")
            params.append(period_type)
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        where = " AND ".join(clauses)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT period_end FROM company_financials
                WHERE {where}
                ORDER BY period_end DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        if row is None:
            return None
        return date.fromisoformat(row["period_end"])

    def needs_refresh(self, ticker: str, ttl_days: int, *, source: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT MAX(fetched_at) AS latest_fetch
                FROM company_financials
                WHERE ticker = ? AND source = ?
                """,
                (ticker.upper(), source),
            ).fetchone()
        if row is None or row["latest_fetch"] is None:
            return True
        try:
            fetched_at = datetime.fromisoformat(row["latest_fetch"])
        except ValueError:
            return True
        fetched_day = fetched_at.date()
        age_days = (date.today() - fetched_day).days
        return age_days > ttl_days

    @staticmethod
    def _row_to_period(row: sqlite3.Row) -> CompanyFinancialPeriod:
        return CompanyFinancialPeriod(
            ticker=row["ticker"],
            period_end=date.fromisoformat(row["period_end"]),
            period_type=row["period_type"],  # type: ignore[arg-type]
            source=row["source"],
            currency=row["currency"],
            total_revenue=row["total_revenue"],
            net_income=row["net_income"],
            net_income_incl_nci=row["net_income_incl_nci"],
            interest_income=row["interest_income"],
            operating_income=row["operating_income"],
            eps_basic=row["eps_basic"],
            eps_diluted=row["eps_diluted"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )
