"""Tests for SQLiteSourceReconciliationReader (DQ-001B)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.application.dto.source_reconciliation_dto import (
    RawCandidateObservationIdentityObservation,
    RawCorporateActionLinkageObservation,
    RawInsiderCacheObservation,
    RawMarketContextSnapshotObservation,
    RawPitCacheObservation,
    RawRegimeObservationsObservation,
    RawSeasonalityObservation,
    RawSignalForwardLabelsLinkageObservation,
    RawStockMetaObservation,
    RawTickerNotationObservation,
)
from src.infrastructure.persistence.sqlite_source_reconciliation_reader import (
    SQLiteSourceReconciliationReader,
)


class _EmptyArtifactReader:
    """DQ-001B-only tests don't exercise signal-artifact tables; this fake
    reports every artifact table as existing-but-empty so it contributes no
    findings and never changes overall PASS/FAIL/WARN status."""

    def observe_candidate_observations_identity(
        self,
    ) -> RawCandidateObservationIdentityObservation:
        return RawCandidateObservationIdentityObservation(exists=True, row_count=0)

    def observe_signal_forward_labels_linkage(
        self,
    ) -> RawSignalForwardLabelsLinkageObservation:
        return RawSignalForwardLabelsLinkageObservation(
            exists=True, row_count=0, linkage_provable=True
        )

    def observe_market_context_snapshot_identity(
        self,
    ) -> RawMarketContextSnapshotObservation:
        return RawMarketContextSnapshotObservation(exists=True, row_count=0)

    def observe_regime_observations_identity(self) -> RawRegimeObservationsObservation:
        return RawRegimeObservationsObservation(exists=True, row_count=0)


class _EmptyEnrichmentReader:
    """DQ-001B-only tests don't exercise enrichment tables; this fake reports
    every enrichment table as existing-but-empty so it contributes only
    harmless INFO findings and never changes overall PASS/FAIL/WARN status."""

    def observe_seasonality(self) -> RawSeasonalityObservation:
        return RawSeasonalityObservation(exists=True, row_count=0)

    def observe_company_fundamentals(self) -> RawPitCacheObservation:
        return RawPitCacheObservation(exists=True, row_count=0)

    def observe_analyst_cache(self) -> RawPitCacheObservation:
        return RawPitCacheObservation(exists=True, row_count=0)

    def observe_insider_cache(self) -> RawInsiderCacheObservation:
        return RawInsiderCacheObservation(exists=True, row_count=0)

    def observe_corporate_action_linkage(self) -> RawCorporateActionLinkageObservation:
        return RawCorporateActionLinkageObservation(
            events_exists=True,
            event_dates_exists=True,
            events_row_count=0,
            event_dates_row_count=0,
        )

    def observe_forward_estimates(self) -> RawPitCacheObservation:
        return RawPitCacheObservation(exists=True, row_count=0)

    def observe_ticker_notation(self) -> RawTickerNotationObservation:
        return RawTickerNotationObservation(exists=True, row_count=0)

    def observe_stock_meta(self) -> RawStockMetaObservation:
        return RawStockMetaObservation(exists=True, row_count=0)


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


def _create_broker_summaries(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE broker_summaries (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'idx',
            foreign_buy_value TEXT NOT NULL,
            foreign_sell_value TEXT NOT NULL,
            foreign_buy_lot INTEGER NOT NULL,
            foreign_sell_lot INTEGER NOT NULL,
            total_value TEXT NOT NULL
        )
        """)


def _create_broker_daily_flow(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE broker_daily_flow (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            broker_code TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'stockbit',
            buy_value TEXT NOT NULL DEFAULT '0',
            sell_value TEXT NOT NULL DEFAULT '0',
            net_value TEXT NOT NULL DEFAULT '0'
        )
        """)


def _create_foreign_flow_points(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE foreign_flow_points (
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            source TEXT NOT NULL,
            net_val TEXT NOT NULL
        )
        """)


@pytest.fixture
def full_schema_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "reconcile.db"
    conn = sqlite3.connect(str(db_path))
    _create_candles(conn)
    _create_broker_summaries(conn)
    _create_broker_daily_flow(conn)
    _create_foreign_flow_points(conn)
    conn.commit()
    conn.close()
    return db_path


def test_missing_database_reports_not_exists():
    reader = SQLiteSourceReconciliationReader(Path("/nonexistent/does_not_exist.db"))

    assert reader.database_exists() is False
    assert reader.observe_candles_ohlc().exists is False


def test_candles_ohlc_violation_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100', '90', '80', '95', 1000, "
        "'idx', 'lots', 'adjusted')"
    )  # high (90) < open (100): invalid
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    raw = reader.observe_candles_ohlc()

    assert raw.exists is True
    assert raw.invalid_ohlc_count == 1
    assert len(raw.invalid_ohlc_samples) == 1


def test_negative_candle_volume_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100', '105', '95', '100', -1, "
        "'idx', 'lots', 'adjusted')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    raw = reader.observe_candles_ohlc()

    assert raw.negative_volume_count == 1


def test_candles_missing_provenance_columns_does_not_crash(tmp_path: Path):
    # Regression: older/legacy candles schemas may predate volume_unit and
    # price_adjustment_policy (added via ALTER TABLE). The reader must treat
    # those rows as unverifiable provenance, not crash on a missing column.
    db_path = tmp_path / "legacy_candles.db"
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
            source TEXT NOT NULL DEFAULT 'unknown'
        )
        """)
    conn.execute(
        "INSERT INTO candles (ticker, date, open, high, low, close, volume, source) "
        "VALUES ('BBCA', '2026-01-02', '100', '105', '95', '100', 10, 'idx')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(db_path)
    raw = reader.observe_candles_ohlc()

    assert raw.exists is True
    assert raw.unknown_provenance_count == 1
    assert raw.volume_unit_distribution == {}
    assert raw.price_adjustment_policy_distribution == {}


def test_candles_missing_ohlc_column_does_not_crash(tmp_path: Path):
    # Regression: a candles table that exists but lacks a required OHLC
    # column (e.g. "high") must produce a structured finding, not an
    # sqlite3.OperationalError crash.
    db_path = tmp_path / "partial_candles.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE candles (ticker TEXT NOT NULL, date TEXT NOT NULL, open TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(db_path)
    raw = reader.observe_candles_ohlc()

    assert raw.exists is True
    assert raw.price_columns_present is False
    assert raw.row_count == 1


def test_use_case_reports_candles_schema_insufficient_finding_not_crash(tmp_path: Path):
    from src.application.use_case.audit_source_reconciliation_use_case import (
        AuditSourceReconciliationUseCase,
    )

    db_path = tmp_path / "partial_candles.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE candles (ticker TEXT NOT NULL, date TEXT NOT NULL, open TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(db_path)
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=lambda: "2026-07-16T00:00:00+00:00",
    )
    response = use_case.execute()

    assert any(
        f.code == "CANDLES_SCHEMA_INSUFFICIENT" and f.severity == "FAIL" for f in response.findings
    )


def test_unknown_candle_provenance_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100', '105', '95', '100', 10, "
        "'unknown', 'lots', 'adjusted')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    raw = reader.observe_candles_ohlc()

    assert raw.unknown_provenance_count == 1
    assert raw.source_distribution.get("unknown") == 1


def test_broker_summary_duplicate_identity_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.executemany(
        "INSERT INTO broker_summaries VALUES (?, ?, ?, '100', '50', 10, 5, '150')",
        [
            ("BBCA", "2026-01-02", "idx"),
            ("BBCA", "2026-01-02", "idx"),
        ],
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    raw = reader.observe_broker_summaries()

    assert raw.duplicate_identity_count == 1
    assert len(raw.duplicate_identity_samples) == 1


def test_broker_summary_negative_values_are_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO broker_summaries VALUES ('BBCA', '2026-01-02', 'idx', '-100', '50', "
        "10, 5, '150')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    raw = reader.observe_broker_summaries()

    assert raw.negative_value_count == 1


def test_broker_summaries_missing_value_columns_does_not_crash(tmp_path: Path):
    # Regression: a broker_summaries table that exists but lacks the value
    # columns (e.g. a malformed/partial migration) must produce a structured
    # finding, not an sqlite3.OperationalError crash.
    db_path = tmp_path / "partial_broker_summaries.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE broker_summaries (ticker TEXT NOT NULL, date TEXT NOT NULL, "
        "source TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO broker_summaries VALUES ('BBCA', '2026-01-02', 'idx')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(db_path)
    raw = reader.observe_broker_summaries()

    assert raw.exists is True
    assert raw.value_columns_present is False
    assert raw.row_count == 1


def test_broker_daily_flow_missing_value_columns_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "partial_broker_daily_flow.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE broker_daily_flow (ticker TEXT NOT NULL, date TEXT NOT NULL, "
        "broker_code TEXT NOT NULL, source TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO broker_daily_flow VALUES ('BBCA', '2026-01-02', 'YP', 'stockbit')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(db_path)
    raw = reader.observe_broker_daily_flow()

    assert raw.exists is True
    assert raw.value_columns_present is False
    assert raw.row_count == 1


def test_use_case_reports_schema_insufficient_finding_not_crash(tmp_path: Path):
    from src.application.use_case.audit_source_reconciliation_use_case import (
        AuditSourceReconciliationUseCase,
    )

    db_path = tmp_path / "partial_broker_summaries.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE broker_summaries (ticker TEXT NOT NULL, date TEXT NOT NULL, "
        "source TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO broker_summaries VALUES ('BBCA', '2026-01-02', 'idx')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(db_path)
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=lambda: "2026-07-16T00:00:00+00:00",
    )
    response = use_case.execute()

    assert any(
        f.code == "BROKER_SUMMARY_SCHEMA_INSUFFICIENT" and f.severity == "FAIL"
        for f in response.findings
    )


def test_tracked_broker_net_mismatch_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO broker_daily_flow VALUES ('BBCA', '2026-01-02', 'YP', 'stockbit', "
        "'100', '50', '999')"  # net_value should be 50, not 999
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    raw = reader.observe_broker_daily_flow()

    assert raw.net_mismatch_count == 1


def test_tracked_broker_duplicate_identity_is_detected(full_schema_db: Path):
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO broker_daily_flow VALUES ('BBCA', '2026-01-02', 'YP', 'stockbit', "
        "'100', '50', '50')"
    )
    conn.execute(
        "INSERT INTO broker_daily_flow VALUES ('BBCA', '2026-01-02', 'YP', 'stockbit', "
        "'100', '50', '50')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    raw = reader.observe_broker_daily_flow()

    assert raw.duplicate_identity_count == 1


def test_tracked_broker_subset_info_always_present_via_use_case(full_schema_db: Path):
    from src.application.use_case.audit_source_reconciliation_use_case import (
        AuditSourceReconciliationUseCase,
    )

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=lambda: "2026-07-16T00:00:00+00:00",
    )
    response = use_case.execute()

    assert any(
        f.code == "TRACKED_BROKER_SUBSET_NOT_FULL_MARKET" and f.severity == "INFO"
        for f in response.findings
    )


def test_foreign_flow_unreconcilable_schema_does_not_crash(tmp_path: Path):
    db_path = tmp_path / "no_ffp.db"
    conn = sqlite3.connect(str(db_path))
    _create_broker_summaries(conn)
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(db_path)
    raw = reader.observe_foreign_flow_reconciliation()

    assert raw.foreign_flow_points_exists is False
    assert raw.foreign_flow_points_schema_sufficient is False


def test_foreign_flow_partial_coverage_is_reported(full_schema_db: Path):
    # Regression: unmatched foreign_flow_points rows (e.g. a different
    # provider like stockbit with no idx-source broker_summaries counterpart)
    # must be surfaced explicitly, not silently excluded from the count.
    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO broker_summaries VALUES ('BBCA', '2026-01-02', 'idx', '100', '50', "
        "10, 5, '150')"
    )
    conn.execute("INSERT INTO foreign_flow_points VALUES ('BBCA', '2026-01-02', 'idx', '50')")
    # Unmatched: different source, no corresponding broker_summaries(source='stockbit') row.
    conn.execute(
        "INSERT INTO foreign_flow_points VALUES ('BBCA', '2026-01-02', 'stockbit', '9999')"
    )
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    raw = reader.observe_foreign_flow_reconciliation()

    assert raw.total_row_count == 2
    assert raw.matched_row_count == 1
    assert raw.unmatched_row_count == 1

    from src.application.use_case.audit_source_reconciliation_use_case import (
        AuditSourceReconciliationUseCase,
    )

    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=lambda: "2026-07-16T00:00:00+00:00",
    )
    response = use_case.execute()

    partial_coverage_findings = [
        f for f in response.findings if f.code == "FOREIGN_FLOW_POINTS_PARTIAL_COVERAGE"
    ]
    assert len(partial_coverage_findings) == 1
    assert partial_coverage_findings[0].severity == "WARN"
    assert partial_coverage_findings[0].mismatch_count == 1
    assert response.status == "WARN"


def test_happy_path_produces_pass_except_tracked_broker_info(full_schema_db: Path):
    from src.application.use_case.audit_source_reconciliation_use_case import (
        AuditSourceReconciliationUseCase,
    )

    conn = sqlite3.connect(str(full_schema_db))
    conn.execute(
        "INSERT INTO candles VALUES ('BBCA', '2026-01-02', '100', '105', '95', '100', 10, "
        "'idx', 'lots', 'adjusted')"
    )
    conn.execute(
        "INSERT INTO broker_summaries VALUES ('BBCA', '2026-01-02', 'idx', '100', '50', "
        "10, 5, '150')"
    )
    conn.execute(
        "INSERT INTO broker_daily_flow VALUES ('BBCA', '2026-01-02', 'YP', 'stockbit', "
        "'100', '50', '50')"
    )
    conn.execute("INSERT INTO foreign_flow_points VALUES ('BBCA', '2026-01-02', 'idx', '50')")
    conn.commit()
    conn.close()

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    use_case = AuditSourceReconciliationUseCase(
        reader,
        enrichment_reader=_EmptyEnrichmentReader(),
        artifact_reader=_EmptyArtifactReader(),
        clock=lambda: "2026-07-16T00:00:00+00:00",
    )
    response = use_case.execute()

    assert response.status == "PASS"
    non_info = [f for f in response.findings if f.severity != "INFO"]
    assert non_info == []


def test_reader_does_not_mutate_database(full_schema_db: Path):
    row_count_before = _row_count(full_schema_db, "candles")
    mtime_before = full_schema_db.stat().st_mtime_ns

    reader = SQLiteSourceReconciliationReader(full_schema_db)
    reader.observe_candles_ohlc()
    reader.observe_broker_summaries()
    reader.observe_broker_daily_flow()
    reader.observe_foreign_flow_reconciliation()

    assert _row_count(full_schema_db, "candles") == row_count_before
    assert full_schema_db.stat().st_mtime_ns == mtime_before


def test_reader_opens_connection_in_read_only_mode(full_schema_db: Path, monkeypatch):
    reader = SQLiteSourceReconciliationReader(full_schema_db)

    real_connect = sqlite3.connect
    captured_uris: list[str] = []

    def spying_connect(database, *args, **kwargs):
        if kwargs.get("uri"):
            captured_uris.append(database)
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", spying_connect)

    reader.observe_candles_ohlc()

    assert captured_uris, "expected a uri=True read-only connection"
    assert all("mode=ro" in uri for uri in captured_uris)

    with real_connect(f"file:{full_schema_db}?mode=ro", uri=True) as ro_conn:
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
