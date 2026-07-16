"""Tests for SQLiteEnrichmentReconciliationReader (DQ-001D)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.infrastructure.persistence.sqlite_enrichment_reconciliation_reader import (
    SQLiteEnrichmentReconciliationReader,
)


def _create_seasonality_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE seasonality_cache (ticker TEXT, year INTEGER, month INTEGER, "
        "avg_return_pct REAL, win_rate_pct REAL, positive_years INTEGER, "
        "total_years INTEGER, back_years INTEGER, source TEXT, fetched_month TEXT, "
        "fetched_at TEXT)"
    )


def _create_company_fundamentals(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE company_fundamentals (ticker TEXT, fetched_date TEXT, "
        "pe_ratio_ttm REAL, roe_ttm REAL, net_profit_margin REAL, "
        "revenue_yoy_growth REAL, piotroski_f_score INTEGER, dividend_yield REAL, "
        "week52_high REAL, week52_low REAL, near_52w_high_rank REAL, "
        "market_cap_idr INTEGER, pbv REAL)"
    )


def _create_analyst_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE analyst_cache (ticker TEXT, buy_count INTEGER, "
        "hold_count INTEGER, sell_count INTEGER, avg_price_target REAL, "
        "current_price REAL, last_updated TEXT, fetched_date TEXT, "
        "price_target_low REAL, price_target_high REAL)"
    )


def _create_insider_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE insider_cache (ticker TEXT, name TEXT, role TEXT, "
        "action_type TEXT, shares INTEGER, price REAL, transaction_date TEXT, "
        "ownership_before_pct REAL, ownership_after_pct REAL, fetched_date TEXT)"
    )


def _create_corporate_action_events(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE corporate_action_events (source TEXT, event_type TEXT, "
        "source_event_id TEXT, ticker TEXT, company_id TEXT, company_name TEXT, "
        "active INTEGER, event_note TEXT, amount_value TEXT, amount_currency TEXT, "
        "ratio_old TEXT, ratio_new TEXT, price TEXT, raw_payload_json TEXT, "
        "fetched_at TEXT, created_at TEXT, updated_at TEXT)"
    )


def _create_corporate_action_event_dates(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE corporate_action_event_dates (source TEXT, event_type TEXT, "
        "source_event_id TEXT, ticker TEXT, date_role TEXT, event_date TEXT, "
        "event_time TEXT, timezone TEXT, fetched_at TEXT)"
    )


def _create_forward_estimates_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE forward_estimates_cache (ticker TEXT, fetched_date TEXT, "
        "forward_eps_1y REAL, revenue_forward_1y REAL, current_price REAL, "
        "forward_pe REAL)"
    )


def _create_ticker_notation_cache(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE ticker_notation_cache (ticker TEXT, status TEXT, "
        "tradeable INTEGER, source TEXT, fetched_date TEXT, fetched_at TEXT)"
    )


def _create_stock_meta(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE stock_meta (ticker TEXT, name TEXT, sector TEXT, "
        "sector_key TEXT, industry TEXT, industry_key TEXT, source TEXT, "
        "fetched_at TEXT, checksum TEXT)"
    )


@pytest.fixture
def full_schema_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "enrichment_reconcile.db"
    conn = sqlite3.connect(str(db_path))
    _create_seasonality_cache(conn)
    _create_company_fundamentals(conn)
    _create_analyst_cache(conn)
    _create_insider_cache(conn)
    _create_corporate_action_events(conn)
    _create_corporate_action_event_dates(conn)
    _create_forward_estimates_cache(conn)
    _create_ticker_notation_cache(conn)
    _create_stock_meta(conn)
    conn.commit()
    conn.close()
    return db_path


def test_missing_database_reports_not_exists():
    reader = SQLiteEnrichmentReconciliationReader(Path("/nonexistent/does_not_exist.db"))

    assert reader.observe_seasonality().exists is False
    assert reader.observe_company_fundamentals().exists is False


def test_missing_enrichment_table_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)

    assert reader.observe_seasonality().exists is False
    assert reader.observe_company_fundamentals().exists is False
    assert reader.observe_analyst_cache().exists is False
    assert reader.observe_insider_cache().exists is False
    linkage = reader.observe_corporate_action_linkage()
    assert linkage.events_exists is False
    assert linkage.event_dates_exists is False
    assert reader.observe_forward_estimates().exists is False
    assert reader.observe_ticker_notation().exists is False
    assert reader.observe_stock_meta().exists is False


# ── partial-schema regression tests: must report, never crash ───────────


def test_seasonality_partial_schema_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_seasonality.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE seasonality_cache (ticker TEXT)")
    conn.execute("INSERT INTO seasonality_cache VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)
    raw = reader.observe_seasonality()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "source" in raw.missing_columns
    assert raw.row_count == 1


def test_seasonality_missing_year_and_month_does_not_crash(tmp_path: Path):
    # Regression: a seasonality_cache table with every column the guard
    # originally checked, but missing year/month (referenced by the sample
    # queries), used to crash with "no such column: year" because those two
    # columns were absent from _SEASONALITY_REQUIRED_COLUMNS.
    db_path = tmp_path / "seasonality_missing_year_month.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE seasonality_cache (ticker TEXT, source TEXT, fetched_at TEXT, "
        "fetched_month TEXT, avg_return_pct REAL, win_rate_pct REAL, "
        "positive_years INTEGER, total_years INTEGER, back_years INTEGER)"
    )
    conn.execute(
        "INSERT INTO seasonality_cache "
        "(ticker, source, fetched_at, fetched_month, avg_return_pct, win_rate_pct, "
        "positive_years, total_years, back_years) "
        "VALUES ('BBCA', NULL, '2026-01-01T00:00:00', '2026-01', 1.0, 1.0, 1, 1, 1)"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)
    raw = reader.observe_seasonality()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "year" in raw.missing_columns
    assert "month" in raw.missing_columns

    from src.application.services.source_reconciliation_enrichment_evaluator import (
        evaluate_seasonality,
    )

    check, findings = evaluate_seasonality(raw)

    assert check.status == "FAIL"
    assert len(findings) == 1
    assert findings[0].code == "SEASONALITY_SCHEMA_INSUFFICIENT"
    assert findings[0].severity == "FAIL"


def test_pit_cache_partial_schema_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_fundamentals.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE company_fundamentals (ticker TEXT)")
    conn.execute("INSERT INTO company_fundamentals VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)
    raw = reader.observe_company_fundamentals()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "fetched_date" in raw.missing_columns
    assert raw.row_count == 1


def test_insider_partial_schema_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_insider.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE insider_cache (ticker TEXT, name TEXT)")
    conn.execute("INSERT INTO insider_cache VALUES ('BBCA', 'John Doe')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)
    raw = reader.observe_insider_cache()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "action_type" in raw.missing_columns
    assert "transaction_date" in raw.missing_columns
    assert "fetched_date" in raw.missing_columns


def test_corporate_action_events_partial_schema_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_corp_action.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE corporate_action_events (source TEXT, ticker TEXT)")
    conn.execute(
        "CREATE TABLE corporate_action_event_dates (source TEXT, event_type TEXT, "
        "source_event_id TEXT, ticker TEXT, date_role TEXT, event_date TEXT, fetched_at TEXT)"
    )
    conn.execute("INSERT INTO corporate_action_events VALUES ('stockbit', 'BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)
    raw = reader.observe_corporate_action_linkage()

    assert raw.events_exists is True
    assert raw.event_dates_exists is True
    assert raw.events_schema_sufficient is False
    assert "event_type" in raw.events_missing_columns
    assert raw.event_dates_schema_sufficient is True


def test_corporate_action_event_dates_partial_schema_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_corp_action_dates.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE corporate_action_events (source TEXT, event_type TEXT, "
        "source_event_id TEXT, ticker TEXT)"
    )
    conn.execute("CREATE TABLE corporate_action_event_dates (source TEXT, ticker TEXT)")
    conn.execute("INSERT INTO corporate_action_event_dates VALUES ('stockbit', 'BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)
    raw = reader.observe_corporate_action_linkage()

    assert raw.events_schema_sufficient is True
    assert raw.event_dates_schema_sufficient is False
    assert "event_date" in raw.event_dates_missing_columns


def test_ticker_notation_partial_schema_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_notation.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE ticker_notation_cache (ticker TEXT)")
    conn.execute("INSERT INTO ticker_notation_cache VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)
    raw = reader.observe_ticker_notation()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "source" in raw.missing_columns
    assert "fetched_date" in raw.missing_columns


def test_stock_meta_partial_schema_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_stock_meta.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE stock_meta (ticker TEXT)")
    conn.execute("INSERT INTO stock_meta VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(db_path)
    raw = reader.observe_stock_meta()

    assert raw.exists is True
    assert raw.schema_sufficient is False
    assert "source" in raw.missing_columns
    assert "fetched_at" in raw.missing_columns
    assert "sector" in raw.missing_columns
    assert "industry" in raw.missing_columns


def test_seasonality_bad_source_and_fetched_at_produces_facts(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO seasonality_cache "
        "(ticker, year, month, source, fetched_month, fetched_at) "
        "VALUES ('BBCA', 2026, 1, NULL, '2026-01', NULL)"
    )
    conn.execute(
        "INSERT INTO seasonality_cache "
        "(ticker, year, month, source, fetched_month, fetched_at) "
        "VALUES ('BBRI', 2026, 1, 'unknown', '2026-01', '2026-01-05T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_seasonality()

    assert raw.invalid_source_count == 2
    assert raw.null_fetched_at_count == 1


def test_seasonality_fetched_month_mismatch_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO seasonality_cache "
        "(ticker, year, month, source, fetched_month, fetched_at) "
        "VALUES ('BBCA', 2026, 1, 'stockbit', '2026-02', '2026-01-05T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_seasonality()

    assert raw.fetched_month_mismatch_count == 1


def test_fundamentals_duplicate_ticker_fetched_date_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO company_fundamentals (ticker, fetched_date, pe_ratio_ttm) "
        "VALUES ('BBCA', '2026-01-02', 10.0)"
    )
    conn.execute(
        "INSERT INTO company_fundamentals (ticker, fetched_date, pe_ratio_ttm) "
        "VALUES ('BBCA', '2026-01-02', 11.0)"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_company_fundamentals()

    assert raw.duplicate_identity_count == 1


def test_fundamentals_all_metrics_null_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO company_fundamentals (ticker, fetched_date) VALUES ('BBCA', '2026-01-02')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_company_fundamentals()

    assert raw.all_metrics_null_count == 1


def test_analyst_missing_fetched_date_produces_fact(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute("INSERT INTO analyst_cache (ticker) VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_analyst_cache()

    assert raw.missing_identity_count == 1


def test_insider_missing_transaction_date_produces_fact(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO insider_cache (ticker, name, action_type, fetched_date) "
        "VALUES ('BBCA', 'John Doe', 'buy', '2026-01-02')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_insider_cache()

    assert raw.missing_identity_count == 1


def test_insider_duplicate_natural_key_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    for _ in range(2):
        conn.execute(
            "INSERT INTO insider_cache "
            "(ticker, name, action_type, transaction_date, fetched_date) "
            "VALUES ('BBCA', 'John Doe', 'buy', '2026-01-01', '2026-01-02')"
        )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_insider_cache()

    assert raw.duplicate_identity_count == 1


def test_corporate_action_date_orphan_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO corporate_action_event_dates "
        "(source, event_type, source_event_id, ticker, date_role, event_date, fetched_at) "
        "VALUES ('stockbit', 'dividend', 'evt1', 'BBCA', 'cum', '2026-01-10', "
        "'2026-01-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_corporate_action_linkage()

    assert raw.orphan_date_rows_count == 1


def test_corporate_action_event_without_dates_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO corporate_action_events "
        "(source, event_type, source_event_id, ticker, active, fetched_at) "
        "VALUES ('stockbit', 'dividend', 'evt1', 'BBCA', 1, '2026-01-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_corporate_action_linkage()

    assert raw.events_without_dates_count == 1


def test_corporate_action_null_event_date_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO corporate_action_events "
        "(source, event_type, source_event_id, ticker, active, fetched_at) "
        "VALUES ('stockbit', 'dividend', 'evt1', 'BBCA', 1, '2026-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO corporate_action_event_dates "
        "(source, event_type, source_event_id, ticker, date_role, event_date, fetched_at) "
        "VALUES ('stockbit', 'dividend', 'evt1', 'BBCA', 'cum', NULL, '2026-01-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_corporate_action_linkage()

    assert raw.null_event_date_count == 1


def test_forward_estimates_all_null_row_produces_fact(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO forward_estimates_cache (ticker, fetched_date) VALUES ('BBCA', '2026-01-02')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_forward_estimates()

    assert raw.all_metrics_null_count == 1


def test_ticker_notation_missing_provenance_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute("INSERT INTO ticker_notation_cache (ticker) VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_ticker_notation()

    assert raw.exists is True
    assert raw.missing_provenance_count == 1


def test_stock_meta_missing_identity_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute("INSERT INTO stock_meta (ticker) VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    raw = reader.observe_stock_meta()

    assert raw.missing_identity_count == 1


def test_reader_does_not_mutate_database(full_schema_db: Path):
    row_count_before = _row_count(full_schema_db, "seasonality_cache")
    mtime_before = full_schema_db.stat().st_mtime_ns

    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)
    reader.observe_seasonality()
    reader.observe_company_fundamentals()
    reader.observe_analyst_cache()
    reader.observe_insider_cache()
    reader.observe_corporate_action_linkage()
    reader.observe_forward_estimates()
    reader.observe_ticker_notation()
    reader.observe_stock_meta()

    assert _row_count(full_schema_db, "seasonality_cache") == row_count_before
    assert full_schema_db.stat().st_mtime_ns == mtime_before


def test_reader_opens_connection_in_read_only_mode(full_schema_db: Path, monkeypatch):
    reader = SQLiteEnrichmentReconciliationReader(full_schema_db)

    real_connect = sqlite3.connect
    captured_uris: list[str] = []

    def spying_connect(database, *args, **kwargs):
        if kwargs.get("uri"):
            captured_uris.append(database)
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spying_connect)

    reader.observe_seasonality()

    assert captured_uris, "expected a uri=True read-only connection"
    assert all("mode=ro" in uri for uri in captured_uris)

    with real_connect(f"file:{full_schema_db}?mode=ro", uri=True) as ro_conn:
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute("INSERT INTO seasonality_cache (ticker) VALUES ('X')")


def _row_count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()
