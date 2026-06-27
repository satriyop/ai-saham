from datetime import date

from src.application.use_case.data_quality_audit_use_case import (
    DataQualityAuditRequest,
    DataQualityAuditUseCase,
    DataQualityRawSnapshot,
    DataQualityTableSnapshot,
)


class FakeReader:
    def __init__(self, snapshot: DataQualityRawSnapshot) -> None:
        self.snapshot = snapshot
        self.requested_tickers: list[str] | None = None

    def load_snapshot(self, tickers: list[str] | None = None) -> DataQualityRawSnapshot:
        self.requested_tickers = tickers
        return self.snapshot


def test_missing_database_fails() -> None:
    reader = FakeReader(
        DataQualityRawSnapshot(
            database_exists=False,
            expected_trading_day=None,
            candles=None,
            broker_summaries_idx=None,
            foreign_flow_stockbit=None,
            broker_daily_flow_stockbit=None,
            stockbit_summary_rows=0,
            unsafe_broker_summary_rows=0,
            bad_candle_rows=0,
            candle_source_columns_present=False,
            unknown_candle_provenance_rows=0,
        )
    )

    response = DataQualityAuditUseCase(reader).execute(DataQualityAuditRequest())

    assert response.status == "fail"
    assert response.fail_count == 1
    assert response.issues[0].code == "MISSING_DATABASE"


def test_warns_for_stale_data_and_degraded_rows() -> None:
    reader = FakeReader(
        DataQualityRawSnapshot(
            database_exists=True,
            expected_trading_day=date(2026, 6, 18),
            candles=DataQualityTableSnapshot(
                table="candles",
                rows=100,
                tickers=2,
                latest=date(2026, 6, 17),
                stale_tickers=1,
            ),
            broker_summaries_idx=DataQualityTableSnapshot(
                table="broker_summaries",
                rows=100,
                tickers=2,
                latest=date(2026, 6, 18),
            ),
            foreign_flow_stockbit=None,
            broker_daily_flow_stockbit=None,
            stockbit_summary_rows=3,
            unsafe_broker_summary_rows=4,
            bad_candle_rows=0,
            candle_source_columns_present=False,
            unknown_candle_provenance_rows=0,
        )
    )

    response = DataQualityAuditUseCase(reader).execute(
        DataQualityAuditRequest(tickers=["bbca", " bbri "])
    )

    assert response.status == "warn"
    assert reader.requested_tickers == ["BBCA", "BBRI"]
    codes = {issue.code for issue in response.issues}
    assert "STALE_CANDLES" in codes
    assert "PARTIAL_STALE_CANDLES" in codes
    assert "DEGRADED_STOCKBIT_SUMMARIES" in codes
    assert "UNSAFE_BROKER_DENOMINATOR" in codes
    assert "MISSING_CANDLE_PROVENANCE" in codes


def test_bad_candles_fail() -> None:
    reader = FakeReader(
        DataQualityRawSnapshot(
            database_exists=True,
            expected_trading_day=date(2026, 6, 18),
            candles=DataQualityTableSnapshot(
                table="candles",
                rows=100,
                tickers=2,
                latest=date(2026, 6, 18),
            ),
            broker_summaries_idx=DataQualityTableSnapshot(
                table="broker_summaries",
                rows=100,
                tickers=2,
                latest=date(2026, 6, 18),
            ),
            foreign_flow_stockbit=None,
            broker_daily_flow_stockbit=None,
            stockbit_summary_rows=0,
            unsafe_broker_summary_rows=0,
            bad_candle_rows=2,
            candle_source_columns_present=True,
            unknown_candle_provenance_rows=0,
        )
    )

    response = DataQualityAuditUseCase(reader).execute(DataQualityAuditRequest())

    assert response.status == "fail"
    assert response.fail_count == 1
    assert response.issues[0].code == "BAD_CANDLE_OHLC"


def test_clean_snapshot_passes() -> None:
    reader = FakeReader(
        DataQualityRawSnapshot(
            database_exists=True,
            expected_trading_day=date(2026, 6, 18),
            candles=DataQualityTableSnapshot(
                table="candles",
                rows=100,
                tickers=2,
                latest=date(2026, 6, 18),
            ),
            broker_summaries_idx=DataQualityTableSnapshot(
                table="broker_summaries",
                rows=100,
                tickers=2,
                latest=date(2026, 6, 18),
            ),
            foreign_flow_stockbit=None,
            broker_daily_flow_stockbit=None,
            stockbit_summary_rows=0,
            unsafe_broker_summary_rows=0,
            bad_candle_rows=0,
            candle_source_columns_present=True,
            unknown_candle_provenance_rows=0,
        )
    )

    response = DataQualityAuditUseCase(reader).execute(DataQualityAuditRequest())

    assert response.status == "pass"
    assert response.issues == ()


def test_enrichment_sentinel_findings_are_informational() -> None:
    reader = FakeReader(
        DataQualityRawSnapshot(
            database_exists=True,
            expected_trading_day=date(2026, 6, 18),
            candles=DataQualityTableSnapshot(
                table="candles",
                rows=100,
                tickers=1,
                latest=date(2026, 6, 18),
            ),
            broker_summaries_idx=DataQualityTableSnapshot(
                table="broker_summaries",
                rows=100,
                tickers=1,
                latest=date(2026, 6, 18),
            ),
            foreign_flow_stockbit=None,
            broker_daily_flow_stockbit=None,
            stockbit_summary_rows=0,
            unsafe_broker_summary_rows=0,
            bad_candle_rows=0,
            candle_source_columns_present=True,
            unknown_candle_provenance_rows=0,
            empty_analyst_rows=1,
            forward_estimates_missing_pe_rows=2,
        )
    )

    response = DataQualityAuditUseCase(reader).execute(DataQualityAuditRequest())

    assert response.status == "pass"
    codes = {issue.code for issue in response.issues}
    assert "EMPTY_ANALYST_SENTINELS" in codes
    assert "FORWARD_ESTIMATES_MISSING_PE" in codes


def test_unknown_candle_provenance_warns() -> None:
    reader = FakeReader(
        DataQualityRawSnapshot(
            database_exists=True,
            expected_trading_day=date(2026, 6, 18),
            candles=DataQualityTableSnapshot(
                table="candles",
                rows=100,
                tickers=2,
                latest=date(2026, 6, 18),
            ),
            broker_summaries_idx=DataQualityTableSnapshot(
                table="broker_summaries",
                rows=100,
                tickers=2,
                latest=date(2026, 6, 18),
            ),
            foreign_flow_stockbit=None,
            broker_daily_flow_stockbit=None,
            stockbit_summary_rows=0,
            unsafe_broker_summary_rows=0,
            bad_candle_rows=0,
            candle_source_columns_present=True,
            unknown_candle_provenance_rows=10,
        )
    )

    response = DataQualityAuditUseCase(reader).execute(DataQualityAuditRequest())

    assert response.status == "warn"
    assert response.issues[0].code == "UNKNOWN_CANDLE_PROVENANCE"
