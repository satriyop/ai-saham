"""
SQLite implementation of FinancialsRepository.

Table: company_financials — multi-period statement rows keyed by statement_kind.
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
    FinancialStatementKind,
)
from src.infrastructure.persistence.sqlite_migration_runner import SqliteMigrationRunner

_NAMESPACE = "company_financials"

_CREATE_FINAL = """
CREATE TABLE IF NOT EXISTS company_financials (
    ticker                  TEXT NOT NULL,
    statement_kind          TEXT NOT NULL,
    period_end              TEXT NOT NULL,
    period_type             TEXT NOT NULL,
    source                  TEXT NOT NULL,
    currency                TEXT,
    total_revenue           INTEGER,
    net_income              INTEGER,
    net_income_incl_nci     INTEGER,
    interest_income         INTEGER,
    operating_income        INTEGER,
    eps_basic               REAL,
    eps_diluted             REAL,
    total_assets            INTEGER,
    total_liabilities       INTEGER,
    stockholders_equity     INTEGER,
    cash_and_equivalents    INTEGER,
    total_debt              INTEGER,
    operating_cash_flow     INTEGER,
    investing_cash_flow     INTEGER,
    financing_cash_flow     INTEGER,
    free_cash_flow          INTEGER,
    capital_expenditure     INTEGER,
    end_cash_position       INTEGER,
    fetched_at              TEXT NOT NULL,
    PRIMARY KEY (ticker, statement_kind, period_end, period_type, source)
)
"""

_INDEX_TICKER = """
CREATE INDEX IF NOT EXISTS idx_company_financials_ticker_kind_period
    ON company_financials (ticker, statement_kind, period_type, period_end DESC)
"""

_INDEX_SOURCE = """
CREATE INDEX IF NOT EXISTS idx_company_financials_source_fetched
    ON company_financials (source, fetched_at)
"""

# Versions 0–2: legacy income-only schema (may already be applied on existing DBs).
# Version 3: rebuild to statement_kind PK + BS/CF columns (handled specially).
_LEGACY_MIGRATIONS: list[tuple[int, str]] = [
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
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        runner = SqliteMigrationRunner(self._db_path)
        runner.run(_NAMESPACE, _LEGACY_MIGRATIONS)
        with self._connect() as conn:
            if not _has_statement_kind_column(conn):
                _rebuild_to_statement_kind_schema(conn)
            conn.execute(_INDEX_TICKER)
            conn.execute(_INDEX_SOURCE)
            conn.execute(
                """
                INSERT OR IGNORE INTO _schema_migrations (namespace, version)
                VALUES (?, ?)
                """,
                (_NAMESPACE, 3),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_many(self, periods: list[CompanyFinancialPeriod]) -> int:
        if not periods:
            return 0
        sql = """
            INSERT INTO company_financials (
                ticker, statement_kind, period_end, period_type, source, currency,
                total_revenue, net_income, net_income_incl_nci,
                interest_income, operating_income, eps_basic, eps_diluted,
                total_assets, total_liabilities, stockholders_equity,
                cash_and_equivalents, total_debt,
                operating_cash_flow, investing_cash_flow, financing_cash_flow,
                free_cash_flow, capital_expenditure, end_cash_position,
                fetched_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?
            )
            ON CONFLICT(ticker, statement_kind, period_end, period_type, source)
            DO UPDATE SET
                currency = excluded.currency,
                total_revenue = excluded.total_revenue,
                net_income = excluded.net_income,
                net_income_incl_nci = excluded.net_income_incl_nci,
                interest_income = excluded.interest_income,
                operating_income = excluded.operating_income,
                eps_basic = excluded.eps_basic,
                eps_diluted = excluded.eps_diluted,
                total_assets = excluded.total_assets,
                total_liabilities = excluded.total_liabilities,
                stockholders_equity = excluded.stockholders_equity,
                cash_and_equivalents = excluded.cash_and_equivalents,
                total_debt = excluded.total_debt,
                operating_cash_flow = excluded.operating_cash_flow,
                investing_cash_flow = excluded.investing_cash_flow,
                financing_cash_flow = excluded.financing_cash_flow,
                free_cash_flow = excluded.free_cash_flow,
                capital_expenditure = excluded.capital_expenditure,
                end_cash_position = excluded.end_cash_position,
                fetched_at = excluded.fetched_at
        """
        rows = [
            (
                p.ticker.upper(),
                p.statement_kind,
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
                p.total_assets,
                p.total_liabilities,
                p.stockholders_equity,
                p.cash_and_equivalents,
                p.total_debt,
                p.operating_cash_flow,
                p.investing_cash_flow,
                p.financing_cash_flow,
                p.free_cash_flow,
                p.capital_expenditure,
                p.end_cash_position,
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
        statement_kind: FinancialStatementKind | None = None,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> list[CompanyFinancialPeriod]:
        clauses = ["ticker = ?"]
        params: list[str] = [ticker.upper()]
        if statement_kind is not None:
            clauses.append("statement_kind = ?")
            params.append(statement_kind)
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
                ORDER BY period_end DESC, statement_kind ASC, period_type ASC
                """,
                params,
            ).fetchall()
        return [self._row_to_period(row) for row in rows]

    def latest_period_end(
        self,
        ticker: str,
        *,
        statement_kind: FinancialStatementKind | None = None,
        period_type: FinancialPeriodType | None = None,
        source: str | None = None,
    ) -> date | None:
        clauses = ["ticker = ?"]
        params: list[str] = [ticker.upper()]
        if statement_kind is not None:
            clauses.append("statement_kind = ?")
            params.append(statement_kind)
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

    def needs_refresh(
        self,
        ticker: str,
        ttl_days: int,
        *,
        source: str,
        statement_kind: FinancialStatementKind,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT MAX(fetched_at) AS latest_fetch
                FROM company_financials
                WHERE ticker = ? AND source = ? AND statement_kind = ?
                """,
                (ticker.upper(), source, statement_kind),
            ).fetchone()
        if row is None or row["latest_fetch"] is None:
            return True
        try:
            fetched_at = datetime.fromisoformat(row["latest_fetch"])
        except ValueError:
            return True
        age_days = (date.today() - fetched_at.date()).days
        return age_days > ttl_days

    @staticmethod
    def _row_to_period(row: sqlite3.Row) -> CompanyFinancialPeriod:
        keys = row.keys()
        return CompanyFinancialPeriod(
            ticker=row["ticker"],
            period_end=date.fromisoformat(row["period_end"]),
            period_type=row["period_type"],  # type: ignore[arg-type]
            statement_kind=row["statement_kind"],  # type: ignore[arg-type]
            source=row["source"],
            currency=row["currency"],
            total_revenue=row["total_revenue"],
            net_income=row["net_income"],
            net_income_incl_nci=row["net_income_incl_nci"],
            interest_income=row["interest_income"],
            operating_income=row["operating_income"],
            eps_basic=row["eps_basic"],
            eps_diluted=row["eps_diluted"],
            total_assets=row["total_assets"] if "total_assets" in keys else None,
            total_liabilities=(row["total_liabilities"] if "total_liabilities" in keys else None),
            stockholders_equity=(
                row["stockholders_equity"] if "stockholders_equity" in keys else None
            ),
            cash_and_equivalents=(
                row["cash_and_equivalents"] if "cash_and_equivalents" in keys else None
            ),
            total_debt=row["total_debt"] if "total_debt" in keys else None,
            operating_cash_flow=(
                row["operating_cash_flow"] if "operating_cash_flow" in keys else None
            ),
            investing_cash_flow=(
                row["investing_cash_flow"] if "investing_cash_flow" in keys else None
            ),
            financing_cash_flow=(
                row["financing_cash_flow"] if "financing_cash_flow" in keys else None
            ),
            free_cash_flow=row["free_cash_flow"] if "free_cash_flow" in keys else None,
            capital_expenditure=(
                row["capital_expenditure"] if "capital_expenditure" in keys else None
            ),
            end_cash_position=(row["end_cash_position"] if "end_cash_position" in keys else None),
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )


def _has_statement_kind_column(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA table_info(company_financials)").fetchall()
    if not rows:
        return False
    names = {row[1] for row in rows}  # name column
    return "statement_kind" in names


def _rebuild_to_statement_kind_schema(conn: sqlite3.Connection) -> None:
    """Rebuild legacy income-only table to statement_kind PK + BS/CF columns."""
    conn.execute("BEGIN")
    try:
        exists = conn.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='company_financials'
            """
        ).fetchone()
        if not exists:
            conn.executescript(_CREATE_FINAL)
            conn.execute("COMMIT")
            return

        conn.execute("ALTER TABLE company_financials RENAME TO company_financials_old")
        conn.executescript(_CREATE_FINAL)
        # Copy legacy income rows; new metric columns stay NULL.
        old_cols = {row[1] for row in conn.execute("PRAGMA table_info(company_financials_old)")}
        # Required legacy columns always present from v0.
        conn.execute(
            """
            INSERT INTO company_financials (
                ticker, statement_kind, period_end, period_type, source, currency,
                total_revenue, net_income, net_income_incl_nci,
                interest_income, operating_income, eps_basic, eps_diluted,
                fetched_at
            )
            SELECT
                ticker,
                'income',
                period_end,
                period_type,
                source,
                currency,
                total_revenue,
                net_income,
                net_income_incl_nci,
                interest_income,
                operating_income,
                eps_basic,
                eps_diluted,
                fetched_at
            FROM company_financials_old
            """
        )
        conn.execute("DROP TABLE company_financials_old")
        # Drop legacy index name if present (recreated under new name).
        if "idx_company_financials_ticker_period" in {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }:
            conn.execute("DROP INDEX IF EXISTS idx_company_financials_ticker_period")
        del old_cols  # silence unused if optimized later
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
