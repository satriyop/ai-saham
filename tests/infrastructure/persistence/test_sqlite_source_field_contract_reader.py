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
    conn.execute("""
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
        """)


def _create_broker_daily_flow(conn: sqlite3.Connection) -> None:
    conn.execute("""
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
        """)


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
    conn.execute("""
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
        """)
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


def test_broker_daily_flow_reports_all_fields_for_tracked_broker_contract(tmp_path: Path, catalog):
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
    assert {
        "ticker",
        "date",
        "broker_code",
        "source",
        "buy_value",
        "sell_value",
        "net_value",
        "buy_lot",
        "sell_lot",
        "net_lot",
    } <= field_names

    contracts = catalog.contracts_for_table("broker_daily_flow")
    ticker_contract = next(c for c in contracts if c.field == "ticker")
    assert "tracked broker subset" in ticker_contract.aggregation


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


def _retired_dq_001a_tables_still_present_and_unaffected(catalog: StaticSourceFieldContractCatalog):
    for table in (
        "candles",
        "broker_summaries",
        "broker_daily_flow",
        "candidate_observations",
        "signal_forward_labels",
    ):
        assert table in catalog.tables()
        assert catalog.contracts_for_table(table)


# ── DQ-001E: signal-artifact and market-context tables ───────────────────


def test_catalog_includes_dq_001e_tables(catalog: StaticSourceFieldContractCatalog):
    tables = catalog.tables()
    assert "market_context_snapshots" in tables
    assert "regime_observations" in tables


def _retired_candidate_observations_config_hash_documents_legacy_semantics(
    catalog: StaticSourceFieldContractCatalog,
):
    contracts = catalog.contracts_for_table("candidate_observations")
    config_hash = next(c for c in contracts if c.field == "config_hash")

    assert config_hash.null_policy == "fail"
    assert "legacy" in config_hash.null_semantics.lower()
    assert "non-canonical" in config_hash.null_semantics.lower()


def _retired_candidate_observations_payload_json_delegates_content_validation(
    catalog: StaticSourceFieldContractCatalog,
):
    contracts = catalog.contracts_for_table("candidate_observations")
    payload_json = next(c for c in contracts if c.field == "payload_json")

    assert payload_json.null_policy == "fail"
    assert "reconciliation" in payload_json.null_semantics.lower()


def test_market_context_snapshots_payload_json_delegates_content_validation(
    catalog: StaticSourceFieldContractCatalog,
):
    contracts = catalog.contracts_for_table("market_context_snapshots")
    factors_json = next(c for c in contracts if c.field == "factors_json")

    assert factors_json.null_policy == "fail"
    assert "reconciliation" in factors_json.null_semantics.lower()


def test_regime_observations_detection_inputs_json_delegates_content_validation(
    catalog: StaticSourceFieldContractCatalog,
):
    contracts = catalog.contracts_for_table("regime_observations")
    detection_inputs_json = next(c for c in contracts if c.field == "detection_inputs_json")

    assert detection_inputs_json.null_policy == "fail"
    assert "reconciliation" in detection_inputs_json.null_semantics.lower()


def test_market_context_snapshots_and_regime_observations_identity_fields_fail(
    catalog: StaticSourceFieldContractCatalog,
):
    mcs_fields = {c.field: c for c in catalog.contracts_for_table("market_context_snapshots")}
    assert mcs_fields["as_of_date"].null_policy == "fail"
    assert mcs_fields["regime"].null_policy == "fail"

    ro_fields = {c.field: c for c in catalog.contracts_for_table("regime_observations")}
    assert ro_fields["observation_date"].null_policy == "fail"
    assert ro_fields["regime"].null_policy == "fail"


def _retired_signal_forward_labels_now_covers_all_live_schema_columns(
    catalog: StaticSourceFieldContractCatalog,
):
    contracts = catalog.contracts_for_table("signal_forward_labels")
    fields = {c.field for c in contracts}
    for expected in (
        "days_to_peak",
        "days_to_trough",
        "stop_would_trigger",
        "target_would_trigger",
        "created_at",
        "updated_at",
    ):
        assert expected in fields


_DQ_001E_TABLES = ("market_context_snapshots", "regime_observations")


def _minimal_dq_001e_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE market_context_snapshots (as_of_date TEXT, regime TEXT, "
        "conviction REAL, signal_multiplier REAL, gate_tightening INTEGER, "
        "factors_json TEXT, staleness_warning TEXT, coverage_warning TEXT, "
        "created_at TEXT, regime_confidence REAL, regime_stability TEXT, "
        "days_in_regime INTEGER, transition_warning TEXT)"
    )
    conn.execute(
        "CREATE TABLE regime_observations (observation_date TEXT, schema_version INTEGER, "
        "regime TEXT, regime_score REAL, regime_confidence REAL, regime_stability TEXT, "
        "days_in_regime INTEGER, transition_warning TEXT, detection_inputs_json TEXT, "
        "forward_ihsg_return_5d REAL, forward_ihsg_return_10d REAL, "
        "forward_ihsg_return_20d REAL, created_at TEXT, updated_at TEXT)"
    )


def _create_candidate_observations_with_identity_columns(
    conn: sqlite3.Connection,
) -> None:
    conn.execute("""
        CREATE TABLE candidate_observations (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                   TEXT    NOT NULL,
            snapshot_date            TEXT    NOT NULL,
            captured_at              TEXT    NOT NULL,
            schema_version           INTEGER NOT NULL,
            payload_json             TEXT    NOT NULL,
            workflow                 TEXT    NOT NULL DEFAULT '',
            window_sessions          INTEGER NOT NULL DEFAULT 0,
            data_as_of_date          TEXT    NOT NULL DEFAULT '',
            config_hash              TEXT    NOT NULL DEFAULT '',
            decision_at              TEXT    NOT NULL DEFAULT '',
            latest_completed_session TEXT    NOT NULL DEFAULT '',
            analysis_as_of           TEXT    NOT NULL DEFAULT '',
            market_session_name      TEXT    NOT NULL DEFAULT '',
            is_eod_pending           INTEGER,
            resolution_source        TEXT    NOT NULL DEFAULT '',
            resolution_notes_json    TEXT    NOT NULL DEFAULT '[]',
            artifact_id              TEXT    NOT NULL DEFAULT '',
            semantic_compatibility_id TEXT   NOT NULL DEFAULT '',
            artifact_provenance_json TEXT   NOT NULL DEFAULT ''
        )
        """)


def _retired_artifact_identity_empty_strings_produce_warn_invalid_value(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    """Transitional empty identity strings must produce INVALID_FIELD_VALUE
    at WARN severity, not PASS silently."""
    db_path = tmp_path / "empty_identity.db"
    conn = sqlite3.connect(str(db_path))
    _create_candidate_observations_with_identity_columns(conn)
    conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json,
             workflow, window_sessions, data_as_of_date, config_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BBCA", "2026-07-03", "2026-07-03T09:00:00", 1, "{}", "", 0, "", ""),
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(
        reader=reader, catalog=catalog, clock=lambda: "2026-07-16T00:00:00+00:00"
    )
    response = use_case.execute()

    for field in ("artifact_id", "semantic_compatibility_id", "artifact_provenance_json"):
        findings = [
            f for f in response.findings if f.field == field and f.code == "INVALID_FIELD_VALUE"
        ]
        assert len(findings) == 1, (
            f"Expected one INVALID_FIELD_VALUE for {field}, got {len(findings)}"
        )
        assert findings[0].severity == "WARN", (
            f"{field} empty string should be WARN, got {findings[0].severity}"
        )


def test_artifact_identity_populated_produces_no_findings(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    """Populated canonical artifact identity must produce no findings for
    the three identity columns."""
    db_path = tmp_path / "populated_identity.db"
    conn = sqlite3.connect(str(db_path))
    _create_candidate_observations_with_identity_columns(conn)
    conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json,
             workflow, window_sessions, data_as_of_date, config_hash,
             artifact_id, semantic_compatibility_id, artifact_provenance_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "BBCA",
            "2026-07-03",
            "2026-07-03T09:00:00",
            3,
            "{}",
            "screen_accum",
            7,
            "2026-07-03",
            "abc123",
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            '{"analysis_as_of":"2026-07-03","application_revision":"abc1234",'
            '"captured_at":"2026-07-03T09:30:00.456789Z",'
            '"complete_authority_registry_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
            '"complete_config_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
            '"decision_at":"2026-07-03T16:00:00.123456Z",'
            '"idx_calendar_version":"2026-v3",'
            '"invocation_actor":null,"invocation_command":null,'
            '"latest_completed_session":"2026-07-03",'
            '"session_rule_version":"sr-v2",'
            '"sources":[{"available_at":"2026-07-03T07:00:00.000000Z",'
            '"cutoff_at":"2026-07-03T08:00:00.000000Z",'
            '"observed_through":"2026-07-03",'
            '"provider":"idx","source_family":"exchange",'
            '"source_snapshot_id":"snap-001"}],'
            '"universe_snapshot_id":"univ-001"}',
        ),
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(
        reader=reader, catalog=catalog, clock=lambda: "2026-07-16T00:00:00+00:00"
    )
    response = use_case.execute()

    for field in ("artifact_id", "semantic_compatibility_id", "artifact_provenance_json"):
        findings = [f for f in response.findings if f.field == field]
        assert len(findings) == 0, (
            f"Expected no findings for {field} with populated identity, "
            f"got {len(findings)}: {[f.code for f in findings]}"
        )


def _retired_artifact_identity_null_produces_fail(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    """Actual NULL in an identity column must produce FAIL (null_policy='fail')."""
    db_path = tmp_path / "null_identity.db"
    conn = sqlite3.connect(str(db_path))
    # Create table with NULLABLE identity columns to simulate corruption
    conn.execute("""
        CREATE TABLE candidate_observations (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                   TEXT    NOT NULL,
            snapshot_date            TEXT    NOT NULL,
            captured_at              TEXT    NOT NULL,
            schema_version           INTEGER NOT NULL,
            payload_json             TEXT    NOT NULL,
            workflow                 TEXT    NOT NULL DEFAULT '',
            window_sessions          INTEGER NOT NULL DEFAULT 0,
            data_as_of_date          TEXT    NOT NULL DEFAULT '',
            config_hash              TEXT    NOT NULL DEFAULT '',
            decision_at              TEXT    NOT NULL DEFAULT '',
            latest_completed_session TEXT    NOT NULL DEFAULT '',
            analysis_as_of           TEXT    NOT NULL DEFAULT '',
            market_session_name      TEXT    NOT NULL DEFAULT '',
            is_eod_pending           INTEGER,
            resolution_source        TEXT    NOT NULL DEFAULT '',
            resolution_notes_json    TEXT    NOT NULL DEFAULT '[]',
            artifact_id              TEXT,
            semantic_compatibility_id TEXT,
            artifact_provenance_json TEXT
        )
        """)
    conn.execute(
        """
        INSERT INTO candidate_observations
            (ticker, snapshot_date, captured_at, schema_version, payload_json,
             workflow, window_sessions, data_as_of_date, config_hash,
             artifact_id, semantic_compatibility_id, artifact_provenance_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("BBCA", "2026-07-03", "2026-07-03T09:00:00", 1, "{}", "", 0, "", "", None, None, None),
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(
        reader=reader, catalog=catalog, clock=lambda: "2026-07-16T00:00:00+00:00"
    )
    response = use_case.execute()

    for field in ("artifact_id", "semantic_compatibility_id", "artifact_provenance_json"):
        null_findings = [
            f for f in response.findings if f.field == field and f.code == "NULLS_IN_REQUIRED_FIELD"
        ]
        invalid_findings = [
            f for f in response.findings if f.field == field and f.code == "INVALID_FIELD_VALUE"
        ]
        assert len(null_findings) == 1, (
            f"Expected NULLS_IN_REQUIRED_FIELD for {field} (null), got {len(null_findings)}"
        )
        assert null_findings[0].severity == "FAIL", (
            f"NULL in {field} should be FAIL, got {null_findings[0].severity}"
        )
        # NULL also counts as an invalid value (reader counts IS NULL + invalid values together)
        assert len(invalid_findings) == 1, (
            f"Expected INVALID_FIELD_VALUE for {field} (null+empty), got {len(invalid_findings)}"
        )


# ── ARTIFACT-IDENTITY Slice 4: signal_forward_labels identity audits ─────


def _create_signal_forward_labels_with_identity(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE signal_forward_labels (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                   TEXT    NOT NULL,
            signal_date              TEXT    NOT NULL,
            horizon                  TEXT    NOT NULL,
            observation_captured_at  TEXT    NOT NULL DEFAULT '',
            entry_reference_price    TEXT,
            label_window_start       TEXT,
            label_window_end         TEXT,
            close_return             REAL,
            max_forward_return       REAL,
            max_adverse_excursion    REAL,
            days_to_peak             INTEGER,
            days_to_trough           INTEGER,
            stop_would_trigger       INTEGER,
            target_would_trigger     INTEGER,
            outcome_label            TEXT    NOT NULL,
            unavailable_reason       TEXT,
            fingerprint_json         TEXT    NOT NULL,
            schema_version           INTEGER NOT NULL DEFAULT 1,
            created_at               TEXT    NOT NULL,
            updated_at               TEXT    NOT NULL,
            decision_at              TEXT    NOT NULL DEFAULT '',
            latest_completed_session TEXT    NOT NULL DEFAULT '',
            analysis_as_of           TEXT    NOT NULL DEFAULT '',
            market_session_name      TEXT    NOT NULL DEFAULT '',
            is_eod_pending           INTEGER,
            resolution_source        TEXT    NOT NULL DEFAULT '',
            resolution_notes_json    TEXT    NOT NULL DEFAULT '[]',
            artifact_id              TEXT    NOT NULL DEFAULT '',
            semantic_compatibility_id TEXT   NOT NULL DEFAULT '',
            artifact_provenance_json TEXT   NOT NULL DEFAULT ''
        )
        """)


def _retired_signal_forward_labels_empty_identity_produces_warn_invalid_value(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    """Empty identity strings in signal_forward_labels must produce
    INVALID_FIELD_VALUE at WARN severity, not PASS silently."""
    db_path = tmp_path / "empty_label_identity.db"
    conn = sqlite3.connect(str(db_path))
    _create_signal_forward_labels_with_identity(conn)
    conn.execute(
        """
        INSERT INTO signal_forward_labels
            (ticker, signal_date, horizon, observation_captured_at,
             outcome_label, fingerprint_json, schema_version, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "BBCA",
            "2026-07-01",
            "SWING_10D",
            "2026-07-01T09:00:00",
            "SUCCESS",
            '{"v":1}',
            2,
            "2026-07-16T00:00:00",
            "2026-07-16T00:00:00",
        ),
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(
        reader=reader, catalog=catalog, clock=lambda: "2026-07-16T00:00:00+00:00"
    )
    response = use_case.execute()

    for field in ("artifact_id", "semantic_compatibility_id", "artifact_provenance_json"):
        findings = [
            f
            for f in response.findings
            if f.table == "signal_forward_labels"
            and f.field == field
            and f.code == "INVALID_FIELD_VALUE"
        ]
        assert len(findings) == 1, (
            f"Expected one INVALID_FIELD_VALUE for signal_forward_labels.{field}, "
            f"got {len(findings)}"
        )
        assert findings[0].severity == "WARN", (
            f"signal_forward_labels.{field} empty string should be WARN, got {findings[0].severity}"
        )


def test_signal_forward_labels_populated_identity_produces_no_findings(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    """Populated canonical artifact identity on labels must produce no
    findings for the three identity columns."""
    db_path = tmp_path / "populated_label_identity.db"
    conn = sqlite3.connect(str(db_path))
    _create_signal_forward_labels_with_identity(conn)
    conn.execute(
        """
        INSERT INTO signal_forward_labels
            (ticker, signal_date, horizon, observation_captured_at,
             outcome_label, fingerprint_json, schema_version, created_at, updated_at,
             artifact_id, semantic_compatibility_id, artifact_provenance_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "BBCA",
            "2026-07-01",
            "SWING_10D",
            "2026-07-01T09:00:00",
            "SUCCESS",
            '{"v":1}',
            2,
            "2026-07-16T00:00:00",
            "2026-07-16T00:00:00",
            "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            '{"analysis_as_of":"2026-07-01","application_revision":"abc1234",'
            '"captured_at":"2026-07-01T09:30:00.456789Z",'
            '"complete_authority_registry_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
            '"complete_config_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
            '"decision_at":"2026-07-01T16:00:00.123456Z",'
            '"idx_calendar_version":"2026-v3",'
            '"invocation_actor":null,"invocation_command":null,'
            '"latest_completed_session":"2026-07-01",'
            '"session_rule_version":"sr-v2",'
            '"sources":[{"available_at":"2026-07-01T07:00:00.000000Z",'
            '"cutoff_at":"2026-07-01T08:00:00.000000Z",'
            '"observed_through":"2026-07-01",'
            '"provider":"idx","source_family":"exchange",'
            '"source_snapshot_id":"snap-001"}],'
            '"universe_snapshot_id":"univ-001"}',
        ),
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(
        reader=reader, catalog=catalog, clock=lambda: "2026-07-16T00:00:00+00:00"
    )
    response = use_case.execute()

    for field in ("artifact_id", "semantic_compatibility_id", "artifact_provenance_json"):
        findings = [
            f for f in response.findings if f.table == "signal_forward_labels" and f.field == field
        ]
        assert len(findings) == 0, (
            f"Expected no findings for signal_forward_labels.{field} "
            f"with populated identity, got {len(findings)}: {[f.code for f in findings]}"
        )


def _retired_signal_forward_labels_nullable_identity_produces_fail(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    """Actual NULL in label identity columns must produce FAIL findings."""
    db_path = tmp_path / "null_label_identity.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE signal_forward_labels (
            id                       INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                   TEXT    NOT NULL,
            signal_date              TEXT    NOT NULL,
            horizon                  TEXT    NOT NULL,
            observation_captured_at  TEXT    NOT NULL DEFAULT '',
            entry_reference_price    TEXT,
            label_window_start       TEXT,
            label_window_end         TEXT,
            close_return             REAL,
            max_forward_return       REAL,
            max_adverse_excursion    REAL,
            days_to_peak             INTEGER,
            days_to_trough           INTEGER,
            stop_would_trigger       INTEGER,
            target_would_trigger     INTEGER,
            outcome_label            TEXT    NOT NULL,
            unavailable_reason       TEXT,
            fingerprint_json         TEXT    NOT NULL,
            schema_version           INTEGER NOT NULL DEFAULT 1,
            created_at               TEXT    NOT NULL,
            updated_at               TEXT    NOT NULL,
            decision_at              TEXT    NOT NULL DEFAULT '',
            latest_completed_session TEXT    NOT NULL DEFAULT '',
            analysis_as_of           TEXT    NOT NULL DEFAULT '',
            market_session_name      TEXT    NOT NULL DEFAULT '',
            is_eod_pending           INTEGER,
            resolution_source        TEXT    NOT NULL DEFAULT '',
            resolution_notes_json    TEXT    NOT NULL DEFAULT '[]',
            artifact_id              TEXT,
            semantic_compatibility_id TEXT,
            artifact_provenance_json TEXT
        )
        """)
    conn.execute(
        """
        INSERT INTO signal_forward_labels
            (ticker, signal_date, horizon, observation_captured_at,
             outcome_label, fingerprint_json, schema_version, created_at, updated_at,
             artifact_id, semantic_compatibility_id, artifact_provenance_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "BBCA",
            "2026-07-01",
            "SWING_10D",
            "2026-07-01T09:00:00",
            "SUCCESS",
            '{"v":1}',
            2,
            "2026-07-16T00:00:00",
            "2026-07-16T00:00:00",
            None,
            None,
            None,
        ),
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(
        reader=reader, catalog=catalog, clock=lambda: "2026-07-16T00:00:00+00:00"
    )
    response = use_case.execute()

    for field in ("artifact_id", "semantic_compatibility_id", "artifact_provenance_json"):
        null_findings = [
            f
            for f in response.findings
            if f.table == "signal_forward_labels"
            and f.field == field
            and f.code == "NULLS_IN_REQUIRED_FIELD"
        ]
        assert len(null_findings) == 1, (
            f"Expected NULLS_IN_REQUIRED_FIELD for signal_forward_labels.{field}, "
            f"got {len(null_findings)}"
        )
        assert null_findings[0].severity == "FAIL", (
            f"NULL in signal_forward_labels.{field} should be FAIL, got {null_findings[0].severity}"
        )


_VALID_SHA256_AAA = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_VALID_SHA256_BBB = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

_VALID_CANONICAL_PROVENANCE = (
    '{"analysis_as_of":"2026-07-01","application_revision":"abc1234",'
    '"captured_at":"2026-07-01T09:30:00.456789Z",'
    '"complete_authority_registry_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
    '"complete_config_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
    '"decision_at":"2026-07-01T16:00:00.123456Z",'
    '"idx_calendar_version":"2026-v3",'
    '"invocation_actor":null,"invocation_command":null,'
    '"latest_completed_session":"2026-07-01",'
    '"session_rule_version":"sr-v2",'
    '"sources":[{"available_at":"2026-07-01T07:00:00.000000Z",'
    '"cutoff_at":"2026-07-01T08:00:00.000000Z",'
    '"observed_through":"2026-07-01",'
    '"provider":"idx","source_family":"exchange",'
    '"source_snapshot_id":"snap-001"}],'
    '"universe_snapshot_id":"univ-001"}'
)

_DUPLICATE_SOURCE_PROVENANCE = (
    '{"analysis_as_of":"2026-07-01","application_revision":"abc1234",'
    '"captured_at":"2026-07-01T09:30:00.456789Z",'
    '"complete_authority_registry_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
    '"complete_config_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
    '"decision_at":"2026-07-01T16:00:00.123456Z",'
    '"idx_calendar_version":"2026-v3",'
    '"invocation_actor":null,"invocation_command":null,'
    '"latest_completed_session":"2026-07-01",'
    '"session_rule_version":"sr-v2",'
    '"sources":[{"available_at":"2026-07-01T07:00:00.000000Z",'
    '"cutoff_at":"2026-07-01T08:00:00.000000Z",'
    '"observed_through":"2026-07-01",'
    '"provider":"idx","source_family":"exchange",'
    '"source_snapshot_id":"snap-001"},'
    '{"available_at":"2026-07-01T07:00:00.000000Z",'
    '"cutoff_at":"2026-07-01T08:00:00.000000Z",'
    '"observed_through":"2026-07-01",'
    '"provider":"idx","source_family":"exchange",'
    '"source_snapshot_id":"snap-001"}],'
    '"universe_snapshot_id":"univ-001"}'
)


def _verify_identity_audit(
    tmp_path: Path,
    catalog: StaticSourceFieldContractCatalog,
    table: str,
    identity_values: tuple[str, str, str],
    *,
    expect_identity_finding: bool = True,
) -> int:
    """Create a temp DB with schema for *table*, insert one row with the given
    identity triplet, run the audit, and check INVALID_ARTIFACT_IDENTITY.

    Returns the finding count (caller can assert == 0 or == 1).
    """
    db_path = tmp_path / f"{table}_identity_audit.db"
    conn = sqlite3.connect(str(db_path))

    if table == "signal_forward_labels":
        _create_signal_forward_labels_with_identity(conn)
        insert_sql = """
            INSERT INTO signal_forward_labels
                (ticker, signal_date, horizon, observation_captured_at,
                 outcome_label, fingerprint_json, schema_version, created_at, updated_at,
                 artifact_id, semantic_compatibility_id, artifact_provenance_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            "BBCA",
            "2026-07-01",
            "SWING_10D",
            "2026-07-01T09:00:00",
            "SUCCESS",
            '{"v":1}',
            2,
            "2026-07-16T00:00:00",
            "2026-07-16T00:00:00",
            *identity_values,
        )
    else:
        _create_candidate_observations_with_identity_columns(conn)
        insert_sql = """
            INSERT INTO candidate_observations
                (ticker, snapshot_date, captured_at, schema_version, payload_json,
                 workflow, window_sessions, data_as_of_date, config_hash,
                 artifact_id, semantic_compatibility_id, artifact_provenance_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            "BBCA",
            "2026-07-03",
            "2026-07-03T09:00:00",
            3,
            "{}",
            "screen_accum",
            7,
            "2026-07-03",
            "abc123",
            *identity_values,
        )

    conn.execute(insert_sql, params)
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)
    use_case = AuditSourceFieldContractsUseCase(
        reader=reader, catalog=catalog, clock=lambda: "2026-07-16T00:00:00+00:00"
    )
    response = use_case.execute()

    findings = [
        f for f in response.findings if f.table == table and f.code == "INVALID_ARTIFACT_IDENTITY"
    ]
    if expect_identity_finding:
        assert len(findings) == 1, (
            f"Expected one INVALID_ARTIFACT_IDENTITY for {table} with "
            f"identity=({identity_values[0][:20]}..., {identity_values[1][:20]}..., "
            f"{identity_values[2][:40]}...), got {len(findings)}"
        )
        assert findings[0].severity == "FAIL", (
            f"INVALID_ARTIFACT_IDENTITY should be FAIL, got {findings[0].severity}"
        )
        return 1
    else:
        assert len(findings) == 0, (
            f"Expected no INVALID_ARTIFACT_IDENTITY for {table}, got {len(findings)}: {findings}"
        )
        return 0


# ── signal_forward_labels malformed identity tests ──────────────────────


@pytest.mark.parametrize(
    "aid,sid,prov,desc",
    [
        pytest.param(
            "sha256:not-a-valid-hex-string",
            _VALID_SHA256_BBB,
            _VALID_CANONICAL_PROVENANCE,
            "malformed SHA-256 hash in artifact_id",
            id="malformed-hash",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            "not-valid-json-at-all",
            "non-JSON string in provenance",
            id="malformed-json",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            "[1, 2, 3]",
            "JSON array instead of provenance dict",
            id="json-array-not-dict",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            '{"anything":"goes"}',
            "valid JSON object but wrong schema (missing all provenance keys)",
            id="wrong-schema-object",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            '{"application_revision":"abc1234","analysis_as_of":"2026-07-01",'
            '"captured_at":"2026-07-01T09:30:00.456789Z",'
            '"complete_authority_registry_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
            '"complete_config_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
            '"decision_at":"2026-07-01T16:00:00.123456Z",'
            '"idx_calendar_version":"2026-v3",'
            '"invocation_actor":null,"invocation_command":null,'
            '"latest_completed_session":"2026-07-01",'
            '"session_rule_version":"sr-v2",'
            '"sources":[{"available_at":"2026-07-01T07:00:00.000000Z",'
            '"cutoff_at":"2026-07-01T08:00:00.000000Z",'
            '"observed_through":"2026-07-01",'
            '"provider":"idx","source_family":"exchange",'
            '"source_snapshot_id":"snap-001"}],'
            '"universe_snapshot_id":"univ-001"}',
            "non-canonical key ordering (application_revision before analysis_as_of)",
            id="noncanonical-key-order",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            '{"analysis_as_of":"2026-07-01","application_revision":"abc1234",'
            '"captured_at":"2026-07-01T09:30:00.456789Z",'
            '"complete_authority_registry_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
            '"complete_config_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
            '"decision_at":"2026-07-01T16:00:00.123456Z",'
            '"extra_key":"oops",'
            '"idx_calendar_version":"2026-v3",'
            '"invocation_actor":null,"invocation_command":null,'
            '"latest_completed_session":"2026-07-01",'
            '"session_rule_version":"sr-v2",'
            '"sources":[{"available_at":"2026-07-01T07:00:00.000000Z",'
            '"cutoff_at":"2026-07-01T08:00:00.000000Z",'
            '"observed_through":"2026-07-01",'
            '"provider":"idx","source_family":"exchange",'
            '"source_snapshot_id":"snap-001"}],'
            '"universe_snapshot_id":"univ-001"}',
            "extra provenance key",
            id="extra-keys",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            '{"sources":[]}',
            "valid JSON dict but missing most provenance keys",
            id="missing-keys",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            '{"analysis_as_of":"2026-07-01","application_revision":"abc1234",'
            '"captured_at":"not-a-timestamp",'
            '"complete_authority_registry_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
            '"complete_config_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
            '"decision_at":"2026-07-01T16:00:00.123456Z",'
            '"idx_calendar_version":"2026-v3",'
            '"invocation_actor":null,"invocation_command":null,'
            '"latest_completed_session":"2026-07-01",'
            '"session_rule_version":"sr-v2",'
            '"sources":[{"available_at":"2026-07-01T07:00:00.000000Z",'
            '"cutoff_at":"2026-07-01T08:00:00.000000Z",'
            '"observed_through":"2026-07-01",'
            '"provider":"idx","source_family":"exchange",'
            '"source_snapshot_id":"snap-001"}],'
            '"universe_snapshot_id":"univ-001"}',
            "invalid timestamp in provenance",
            id="invalid-timestamp",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            '{"analysis_as_of":"2026-07-01","application_revision":"abc1234",'
            '"captured_at":"2026-07-01T09:30:00.456789Z",'
            '"complete_authority_registry_hash":"not-a-64-hex-hash",'
            '"complete_config_hash":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
            '"decision_at":"2026-07-01T16:00:00.123456Z",'
            '"idx_calendar_version":"2026-v3",'
            '"invocation_actor":null,"invocation_command":null,'
            '"latest_completed_session":"2026-07-01",'
            '"session_rule_version":"sr-v2",'
            '"sources":[{"available_at":"2026-07-01T07:00:00.000000Z",'
            '"cutoff_at":"2026-07-01T08:00:00.000000Z",'
            '"observed_through":"2026-07-01",'
            '"provider":"idx","source_family":"exchange",'
            '"source_snapshot_id":"snap-001"}],'
            '"universe_snapshot_id":"univ-001"}',
            "invalid nested hash (authority registry hash not 64 hex)",
            id="invalid-nested-hash",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            _DUPLICATE_SOURCE_PROVENANCE,
            "duplicate source entries",
            id="duplicate-sources",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            "",
            "",
            "partial triplet: artifact_id populated, others empty",
            id="partial-triplet",
        ),
    ],
)
def _retired_signal_forward_labels_malformed_artifact_identity(
    tmp_path: Path,
    catalog: StaticSourceFieldContractCatalog,
    aid: str,
    sid: str,
    prov: str,
    desc: str,
):
    _verify_identity_audit(
        tmp_path,
        catalog,
        "signal_forward_labels",
        (aid, sid, prov),
        expect_identity_finding=True,
    )


def test_signal_forward_labels_valid_empty_triplet_no_identity_finding(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    """All-empty identity triplet must NOT trigger INVALID_ARTIFACT_IDENTITY."""
    _verify_identity_audit(
        tmp_path,
        catalog,
        "signal_forward_labels",
        ("", "", ""),
        expect_identity_finding=False,
    )


# ── candidate_observations malformed identity tests ─────────────────────


@pytest.mark.parametrize(
    "aid,sid,prov,desc",
    [
        pytest.param(
            "sha256:not-a-valid-hex-string",
            _VALID_SHA256_BBB,
            _VALID_CANONICAL_PROVENANCE,
            "malformed SHA-256 hash in artifact_id",
            id="obs-malformed-hash",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            '{"anything":"goes"}',
            "wrong-schema provenance object",
            id="obs-wrong-schema-object",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            _VALID_SHA256_BBB,
            _DUPLICATE_SOURCE_PROVENANCE,
            "duplicate source entries",
            id="obs-duplicate-sources",
        ),
        pytest.param(
            _VALID_SHA256_AAA,
            "",
            "",
            "partial triplet",
            id="obs-partial-triplet",
        ),
    ],
)
def _retired_candidate_observations_malformed_artifact_identity(
    tmp_path: Path,
    catalog: StaticSourceFieldContractCatalog,
    aid: str,
    sid: str,
    prov: str,
    desc: str,
):
    _verify_identity_audit(
        tmp_path,
        catalog,
        "candidate_observations",
        (aid, sid, prov),
        expect_identity_finding=True,
    )


def test_candidate_observations_valid_empty_triplet_no_identity_finding(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    """All-empty identity triplet must NOT trigger INVALID_ARTIFACT_IDENTITY."""
    _verify_identity_audit(
        tmp_path,
        catalog,
        "candidate_observations",
        ("", "", ""),
        expect_identity_finding=False,
    )


def test_dq_001e_live_schema_fixture_reports_no_missing_table_or_field(
    tmp_path: Path, catalog: StaticSourceFieldContractCatalog
):
    db_path = tmp_path / "dq_001e.db"
    conn = sqlite3.connect(str(db_path))
    _minimal_dq_001e_schema(conn)
    conn.commit()
    conn.close()

    reader = SQLiteSourceFieldContractReader(db_path, catalog=catalog)

    for table in _DQ_001E_TABLES:
        raw = reader.observe_table(table)
        assert raw.exists is True, f"{table} unexpectedly missing"
        observed_fields = {f.field: f for f in raw.fields}
        for contract in catalog.contracts_for_table(table):
            assert contract.field in observed_fields, (
                f"{table}.{contract.field} unexpectedly missing"
            )
            assert observed_fields[contract.field].exists is True
