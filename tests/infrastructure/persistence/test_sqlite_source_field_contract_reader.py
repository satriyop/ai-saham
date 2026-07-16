"""Tests for SQLiteSourceFieldContractReader (DQ-001A)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.application.use_case.audit_source_field_contracts_use_case import (
    AuditSourceFieldContractsUseCase,
)
from src.infrastructure.persistence.source_field_contract_catalog import (
    StaticSourceFieldContractCatalog,
)
from src.infrastructure.persistence.sqlite_source_field_contract_reader import (
    SQLiteSourceFieldContractReader,
)


def _create_candles(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE candles (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open TEXT NOT NULL,
            high TEXT NOT NULL,
            low TEXT NOT NULL,
            close TEXT NOT NULL,
            volume INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'unknown',
            volume_unit TEXT NOT NULL DEFAULT 'unknown',
            price_adjustment_policy TEXT NOT NULL DEFAULT 'unknown'
        )
        """
    )


def _create_broker_daily_flow(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE broker_daily_flow (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            broker_code TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'stockbit',
            buy_lot INTEGER NOT NULL DEFAULT 0,
            sell_lot INTEGER NOT NULL DEFAULT 0,
            net_lot INTEGER NOT NULL DEFAULT 0,
            buy_value TEXT NOT NULL DEFAULT '0',
            sell_value TEXT NOT NULL DEFAULT '0',
            net_value TEXT NOT NULL DEFAULT '0'
        )
        """
    )


def _create_candidate_observations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE candidate_observations (
            ticker TEXT NOT NULL,
            snapshot_date TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            workflow TEXT NOT NULL DEFAULT '',
            window_sessions INTEGER NOT NULL DEFAULT 0,
            data_as_of_date TEXT NOT NULL DEFAULT '',
            config_hash TEXT NOT NULL DEFAULT ''
        )
        """
    )


@pytest.fixture
def catalog() -> StaticSourceFieldContractCatalog:
    return StaticSourceFieldContractCatalog()


def test_valid_candles_passes_field_existence_and_null_checks(tmp_path: Path, catalog):
    db_path = tmp_path / "valid_candles.db"
    conn = sqlite3.connect(str(db_path))
    _create_candles(conn)
    conn.execute(
        "INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100', '105', '99', '104', 1000, "
        "'idx', 'lots', 'adjusted')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    raw = reader.observe_table("candles")

    assert raw.exists is True
    assert raw.row_count == 1
    fields_by_name = {f.field: f for f in raw.fields}
    assert fields_by_name["ticker"].exists is True
    assert fields_by_name["ticker"].null_count == 0
    assert fields_by_name["source"].invalid_value_count == 0


def test_candles_missing_source_column_reports_not_exists(tmp_path: Path, catalog):
    db_path = tmp_path / "missing_source.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE candles (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open TEXT NOT NULL,
            high TEXT NOT NULL,
            low TEXT NOT NULL,
            close TEXT NOT NULL,
            volume INTEGER NOT NULL,
            volume_unit TEXT NOT NULL DEFAULT 'unknown',
            price_adjustment_policy TEXT NOT NULL DEFAULT 'unknown'
        )
        """
    )
    conn.execute(
        "INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100', '105', '99', '104', 1000, "
        "'lots', 'adjusted')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    raw = reader.observe_table("candles")

    source_field = next(f for f in raw.fields if f.field == "source")
    assert source_field.exists is False


def test_candles_source_unknown_value_is_flagged_invalid(tmp_path: Path, catalog):
    db_path = tmp_path / "unknown_source.db"
    conn = sqlite3.connect(str(db_path))
    _create_candles(conn)
    conn.executemany(
        "INSERT INTO candles VALUES (?, ?, '100', '105', '99', '104', 1000, ?, 'lots', 'adjusted')",
        [
            ("BBCA", "2026-01-02", "idx"),
            ("BBRI", "2026-01-02", "unknown"),
        ],
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    raw = reader.observe_table("candles")

    source_field = next(f for f in raw.fields if f.field == "source")
    assert source_field.invalid_value_count == 1


def test_broker_daily_flow_reports_all_fields_for_tracked_broker_contract(
    tmp_path: Path, catalog
):
    db_path = tmp_path / "broker_daily_flow.db"
    conn = sqlite3.connect(str(db_path))
    _create_broker_daily_flow(conn)
    conn.execute(
        "INSERT INTO broker_daily_flow VALUES "
        "('BBCA', '2026-01-02', 'YP', 'stockbit', 100, 50, 50, '1000', '500', '500')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    raw = reader.observe_table("broker_daily_flow")

    assert raw.exists is True
    field_names = {f.field for f in raw.fields}
    assert {"ticker", "date", "broker_code", "source", "buy_value", "sell_value", "net_value",
            "buy_lot", "sell_lot", "net_lot"} <= field_names

    contracts = catalog.contracts_for_table("broker_daily_flow")
    ticker_contract = next(c for c in contracts if c.field == "ticker")
    assert "tracked broker subset" in ticker_contract.aggregation


def test_candidate_observations_empty_config_hash_emits_legacy_warning(tmp_path: Path, catalog):
    db_path = tmp_path / "candidate_observations.db"
    conn = sqlite3.connect(str(db_path))
    _create_candidate_observations(conn)
    conn.executemany(
        "INSERT INTO candidate_observations "
        "(ticker, snapshot_date, captured_at, schema_version, payload_json, workflow, "
        "window_sessions, data_as_of_date, config_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("BBCA", "2026-01-02", "2026-01-02T00:00:00", 1, "{}", "w", 5, "2026-01-02", ""),
            ("BBCA", "2026-01-03", "2026-01-03T00:00:00", 1, "{}", "w", 5, "2026-01-03", "abc123"),
        ],
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    raw = reader.observe_table("candidate_observations")

    assert raw.special_checks["legacy_config_hash_count"] == 1

    use_case = AuditSourceFieldContractsUseCase(
        reader=reader, catalog=catalog, clock=lambda: "2026-07-16T00:00:00+00:00"
    )
    response = use_case.execute()
    legacy_findings = [
        f for f in response.findings if f.code == "LEGACY_NON_CANONICAL_IDENTITY"
    ]
    assert len(legacy_findings) == 1


def test_missing_database_reports_not_exists(catalog):
    reader = SQLiteSourceFieldContractReader(
        Path("/nonexistent/does_not_exist.db"), catalog=catalog
    )

    assert reader.database_exists() is False
    raw = reader.observe_table("candles")
    assert raw.exists is False


def test_reader_does_not_mutate_database(tmp_path: Path, catalog):
    db_path = tmp_path / "no_mutate.db"
    conn = sqlite3.connect(str(db_path))
    _create_candles(conn)
    conn.execute(
        "INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100', '105', '99', '104', 1000, "
        "'idx', 'lots', 'adjusted')"
    )
    conn.commit()
    conn.close()

    row_count_before = _row_count(db_path, "candles")
    mtime_before = db_path.stat().st_mtime_ns

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    for table in catalog.tables():
        reader.observe_table(table)

    row_count_after = _row_count(db_path, "candles")
    mtime_after = db_path.stat().st_mtime_ns

    assert row_count_before == row_count_after
    assert mtime_before == mtime_after


def test_reader_opens_connection_in_read_only_mode(tmp_path: Path, catalog, monkeypatch):
    db_path = tmp_path / "ro_mode.db"
    conn = sqlite3.connect(str(db_path))
    _create_candles(conn)
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)

    real_connect = sqlite3.connect
    captured_uris: list[str] = []

    def spying_connect(database, *args, **kwargs):
        if kwargs.get("uri"):
            captured_uris.append(database)
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spying_connect)

    reader.observe_table("candles")

    assert captured_uris, "expected a uri=True read-only connection"
    assert all("mode=ro" in uri for uri in captured_uris)

    with real_connect(f"file:{db_path}?mode=ro", uri=True) as ro_conn:
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute(
                "INSERT INTO candles (ticker, date, open, high, low, close, volume) "
                "VALUES ('X', '2026-01-01', '1', '1', '1', '1', 1)"
            )


def _row_count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


# ── DQ-001C: enrichment/source-context tables ────────────────────────────

_DQ_001C_TABLES = (
    "analyst_cache",
    "insider_cache",
    "company_fundamentals",
    "shareholding_composition",
    "seasonality_cache",
    "ticker_notation_cache",
    "bandar_detector",
    "corporate_action_events",
    "corporate_action_event_dates",
    "forward_estimates_cache",
    "company_profile_cache",
    "earnings_cache",
    "stock_meta",
)


def test_catalog_includes_all_dq_001c_tables(catalog: StaticSourceFieldContractCatalog):
    tables = catalog.tables()
    for table in _DQ_001C_TABLES:
        assert table in tables


def test_each_dq_001c_table_has_at_least_one_required_fail_field(
    catalog: StaticSourceFieldContractCatalog,
):
    for table in _DQ_001C_TABLES:
        contracts = catalog.contracts_for_table(table)
        assert contracts, f"{table} has no contracts"
        fail_fields = {c.field for c in contracts if c.null_policy == "fail"}
        assert fail_fields, f"{table} has no identity/provenance fail field"
        assert "ticker" in fail_fields


def _minimal_dq_001c_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE analyst_cache (ticker TEXT, buy_count INTEGER, hold_count INTEGER, "
        "sell_count INTEGER, avg_price_target REAL, current_price REAL, last_updated TEXT, "
        "fetched_date TEXT, price_target_low REAL, price_target_high REAL)"
    )
    conn.execute(
        "CREATE TABLE insider_cache (ticker TEXT, name TEXT, role TEXT, action_type TEXT, "
        "shares INTEGER, price REAL, transaction_date TEXT, ownership_before_pct REAL, "
        "ownership_after_pct REAL, fetched_date TEXT)"
    )
    conn.execute(
        "CREATE TABLE company_fundamentals (ticker TEXT, fetched_date TEXT, pe_ratio_ttm REAL, "
        "roe_ttm REAL, net_profit_margin REAL, revenue_yoy_growth REAL, "
        "piotroski_f_score INTEGER, dividend_yield REAL, week52_high REAL, week52_low REAL, "
        "near_52w_high_rank REAL, market_cap_idr INTEGER, pbv REAL)"
    )
    conn.execute(
        "CREATE TABLE shareholding_composition (ticker TEXT, fetched_date TEXT, "
        "report_date TEXT, institution_pct REAL, individual_pct REAL, top_holder_name TEXT, "
        "top_holder_pct REAL, total_shares INTEGER, total_shares_formatted TEXT)"
    )
    conn.execute(
        "CREATE TABLE seasonality_cache (ticker TEXT, year INTEGER, month INTEGER, "
        "avg_return_pct REAL, win_rate_pct REAL, positive_years INTEGER, total_years INTEGER, "
        "back_years INTEGER, source TEXT, fetched_month TEXT, fetched_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE ticker_notation_cache (ticker TEXT, status TEXT, tradeable INTEGER, "
        "listing_board TEXT, sector TEXT, sub_sector TEXT, haircut_percentage TEXT, "
        "notations_json TEXT, market_status TEXT, suspend_info TEXT, "
        "corp_action_active INTEGER, has_uma INTEGER, catalogs_json TEXT, source TEXT, "
        "fetched_date TEXT, fetched_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE bandar_detector (ticker TEXT, session_date TEXT, broker_accdist TEXT, "
        "today_accdist TEXT, five_day_accdist TEXT, top1_accdist TEXT, top1_percent REAL, "
        "today_percent REAL, total_buyer INTEGER, total_seller INTEGER, top3_accdist TEXT, "
        "top5_accdist TEXT, top10_accdist TEXT, number_broker_buysell INTEGER, vwap REAL, "
        "total_value REAL, total_volume INTEGER)"
    )
    conn.execute(
        "CREATE TABLE corporate_action_events (source TEXT, event_type TEXT, "
        "source_event_id TEXT, ticker TEXT, company_id TEXT, company_name TEXT, "
        "active INTEGER, event_note TEXT, amount_value TEXT, amount_currency TEXT, "
        "ratio_old TEXT, ratio_new TEXT, price TEXT, raw_payload_json TEXT, "
        "fetched_at TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE corporate_action_event_dates (source TEXT, event_type TEXT, "
        "source_event_id TEXT, ticker TEXT, date_role TEXT, event_date TEXT, "
        "event_time TEXT, timezone TEXT, fetched_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE forward_estimates_cache (ticker TEXT, fetched_date TEXT, "
        "forward_eps_1y REAL, revenue_forward_1y REAL, current_price REAL, forward_pe REAL)"
    )
    conn.execute(
        "CREATE TABLE company_profile_cache (ticker TEXT, fetched_date TEXT, background TEXT, "
        "listing_board TEXT, ipo_date TEXT, ipo_price INTEGER, ipo_amount TEXT, website TEXT, "
        "email TEXT, office_address TEXT)"
    )
    conn.execute(
        "CREATE TABLE earnings_cache (ticker TEXT, year INTEGER, quarter INTEGER, "
        "eps_actual REAL, eps_estimate REAL, eps_surprise_pct REAL, eps_yoy_change REAL, "
        "eps_prev_year REAL, fetched_date TEXT)"
    )
    conn.execute(
        "CREATE TABLE stock_meta (ticker TEXT, name TEXT, sector TEXT, sector_key TEXT, "
        "industry TEXT, industry_key TEXT, source TEXT, fetched_at TEXT, checksum TEXT)"
    )


@pytest.fixture
def dq_001c_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "dq_001c.db"
    conn = sqlite3.connect(str(db_path))
    _minimal_dq_001c_schema(conn)
    conn.commit()
    conn.close()
    return db_path


def test_live_schema_fixture_reports_no_missing_table_or_field(
    dq_001c_db: Path, catalog: StaticSourceFieldContractCatalog
):
    reader = SQLiteSourceFieldContractReader(dq_001c_db, catalog=catalog)

    for table in _DQ_001C_TABLES:
        raw = reader.observe_table(table)
        assert raw.exists is True, f"{table} unexpectedly missing"
        observed_fields = {f.field: f for f in raw.fields}
        for contract in catalog.contracts_for_table(table):
            assert contract.field in observed_fields, (
                f"{table}.{contract.field} unexpectedly missing"
            )
            assert observed_fields[contract.field].exists is True


def test_analyst_cache_missing_fetched_date_fails(dq_001c_db: Path, catalog):
    conn = sqlite3.connect(str(dq_001c_db))
    conn.execute("DROP TABLE analyst_cache")
    conn.execute(
        "CREATE TABLE analyst_cache (ticker TEXT, buy_count INTEGER, hold_count INTEGER, "
        "sell_count INTEGER, avg_price_target REAL, current_price REAL, last_updated TEXT, "
        "price_target_low REAL, price_target_high REAL)"
    )
    conn.execute("INSERT INTO analyst_cache (ticker) VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(dq_001c_db, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(reader, catalog)
    response = use_case.execute()

    analyst = next(t for t in response.tables if t.table == "analyst_cache")
    fetched_date_field = next(f for f in analyst.fields if f.field == "fetched_date")
    assert fetched_date_field.status == "FAIL"
    assert analyst.contract_status == "FAIL"


def test_insider_cache_missing_transaction_date_and_fetched_date_fails(dq_001c_db: Path, catalog):
    conn = sqlite3.connect(str(dq_001c_db))
    conn.execute("DROP TABLE insider_cache")
    conn.execute(
        "CREATE TABLE insider_cache (ticker TEXT, name TEXT, role TEXT, action_type TEXT, "
        "shares INTEGER, price REAL, ownership_before_pct REAL, ownership_after_pct REAL)"
    )
    conn.execute("INSERT INTO insider_cache (ticker) VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(dq_001c_db, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(reader, catalog)
    response = use_case.execute()

    insider = next(t for t in response.tables if t.table == "insider_cache")
    assert insider.contract_status == "FAIL"
    for missing_field in ("transaction_date", "fetched_date"):
        field_result = next(f for f in insider.fields if f.field == missing_field)
        assert field_result.status == "FAIL"


def test_bandar_detector_missing_session_date_fails(dq_001c_db: Path, catalog):
    conn = sqlite3.connect(str(dq_001c_db))
    conn.execute("DROP TABLE bandar_detector")
    conn.execute(
        "CREATE TABLE bandar_detector (ticker TEXT, broker_accdist TEXT, "
        "top1_percent REAL, total_buyer INTEGER, total_seller INTEGER, vwap REAL)"
    )
    conn.execute("INSERT INTO bandar_detector (ticker) VALUES ('BBCA')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(dq_001c_db, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(reader, catalog)
    response = use_case.execute()

    bandar = next(t for t in response.tables if t.table == "bandar_detector")
    assert bandar.contract_status == "FAIL"
    session_date_field = next(f for f in bandar.fields if f.field == "session_date")
    assert session_date_field.status == "FAIL"


def test_corporate_action_event_dates_missing_event_date_fails(dq_001c_db: Path, catalog):
    conn = sqlite3.connect(str(dq_001c_db))
    conn.execute("DROP TABLE corporate_action_event_dates")
    conn.execute(
        "CREATE TABLE corporate_action_event_dates (source TEXT, event_type TEXT, "
        "source_event_id TEXT, ticker TEXT, date_role TEXT, event_time TEXT, "
        "timezone TEXT, fetched_at TEXT)"
    )
    conn.execute(
        "INSERT INTO corporate_action_event_dates (source, event_type, source_event_id, "
        "ticker, date_role) VALUES ('stockbit', 'dividend', 'evt1', 'BBCA', 'cum')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(dq_001c_db, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(reader, catalog)
    response = use_case.execute()

    dates_table = next(t for t in response.tables if t.table == "corporate_action_event_dates")
    assert dates_table.contract_status == "FAIL"
    event_date_field = next(f for f in dates_table.fields if f.field == "event_date")
    assert event_date_field.status == "FAIL"


def test_analyst_cache_null_avg_price_target_warns_not_fails(dq_001c_db: Path, catalog):
    conn = sqlite3.connect(str(dq_001c_db))
    conn.execute(
        "INSERT INTO analyst_cache (ticker, fetched_date, avg_price_target) "
        "VALUES ('BBCA', '2026-01-02', NULL)"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(dq_001c_db, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(reader, catalog)
    response = use_case.execute()

    analyst = next(t for t in response.tables if t.table == "analyst_cache")
    avg_price_target_field = next(f for f in analyst.fields if f.field == "avg_price_target")
    assert avg_price_target_field.status == "WARN"
    assert analyst.contract_status == "WARN"


def test_company_fundamentals_null_pe_ratio_ttm_warns_not_fails(dq_001c_db: Path, catalog):
    conn = sqlite3.connect(str(dq_001c_db))
    conn.execute(
        "INSERT INTO company_fundamentals (ticker, fetched_date, pe_ratio_ttm) "
        "VALUES ('BBCA', '2026-01-02', NULL)"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(dq_001c_db, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(reader, catalog)
    response = use_case.execute()

    fundamentals = next(t for t in response.tables if t.table == "company_fundamentals")
    pe_field = next(f for f in fundamentals.fields if f.field == "pe_ratio_ttm")
    assert pe_field.status == "WARN"
    assert fundamentals.contract_status == "WARN"


def test_seasonality_cache_fetched_month_is_provenance_not_session_date(
    catalog: StaticSourceFieldContractCatalog,
):
    contracts = catalog.contracts_for_table("seasonality_cache")
    fetched_month = next(c for c in contracts if c.field == "fetched_month")

    assert fetched_month.null_policy == "fail"
    assert "provenance" in fetched_month.temporal_meaning.lower()
    # A real session-date field (e.g. bandar_detector.session_date) reads
    # "IDX trading session date" with no provenance qualifier — fetched_month
    # must not be described the same way.
    assert fetched_month.temporal_meaning.lower() != "idx trading session date"

    year_field = next(c for c in contracts if c.field == "year")
    month_field = next(c for c in contracts if c.field == "month")
    assert "not a fetch date" in year_field.temporal_meaning.lower()
    assert "not a fetch date" in month_field.temporal_meaning.lower()


def test_dq_001a_tables_still_present_and_unaffected(catalog: StaticSourceFieldContractCatalog):
    for table in (
        "candles",
        "broker_summaries",
        "broker_daily_flow",
        "candidate_observations",
        "signal_forward_labels",
    ):
        assert table in catalog.tables()
        assert catalog.contracts_for_table(table)
