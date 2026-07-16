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
