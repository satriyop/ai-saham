"""Tests for BuildSeasonalityCleanupPlanUseCase (DQ-001G dry-run cleanup plan)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.application.use_case.build_seasonality_cleanup_plan_use_case import (
    REASON_ALL_METRICS_NULL,
    REASON_INVALID_SOURCE,
    REASON_MALFORMED_FETCHED_AT,
    REASON_MISSING_FETCHED_AT,
    REASON_SEASONALITY_CACHE_UNAVAILABLE,
    BuildSeasonalityCleanupPlanUseCase,
    RawSeasonalityCacheObservation,
    RawSeasonalityCacheRow,
)
from src.infrastructure.browser.stockbit_seasonality import StockbitSeasonalityProvider
from src.infrastructure.persistence.sqlite_seasonality_cleanup_plan_reader import (
    SQLiteSeasonalityCleanupPlanReader,
)


class _FakeReader:
    def __init__(self, observation: RawSeasonalityCacheObservation, exists: bool = True) -> None:
        self._observation = observation
        self._exists = exists

    def database_exists(self) -> bool:
        return self._exists

    def observe_seasonality_cache(self) -> RawSeasonalityCacheObservation:
        return self._observation


def _row(**overrides) -> RawSeasonalityCacheRow:
    values = dict(
        ticker="BBCA",
        year=2026,
        month=7,
        fetched_month="2026-07",
        fetched_at="2026-07-01T00:00:00",
        source="stockbit",
        avg_return_pct=1.23,
        win_rate_pct=60.0,
        positive_years=3,
        total_years=5,
        back_years=5,
    )
    values.update(overrides)
    return RawSeasonalityCacheRow(**values)


def _clock() -> str:
    return "2026-07-16T00:00:00+00:00"


def test_use_case_returns_pass_when_no_invalid_rows():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(),)))

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.status == "PASS"
    assert response.source_available is True
    assert response.invalid_row_count == 0
    assert response.rows == ()
    assert response.artifact_type == "seasonality_cleanup_plan"
    assert response.schema_version == 1
    assert response.table == "seasonality_cache"
    assert response.dry_run is True
    assert response.proposed_action == "DELETE_INVALID_SEASONALITY_ROW"
    assert response.generated_at == "2026-07-16T00:00:00+00:00"


def test_use_case_returns_fail_when_invalid_rows_exist():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(exists=True, rows=(_row(source=None),))
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.status == "FAIL"
    assert response.source_available is True
    assert response.invalid_row_count == 1


def test_null_source_flagged_invalid_source():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(source=None),)))

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.rows[0].reasons == (REASON_INVALID_SOURCE,)


def test_empty_source_flagged_invalid_source():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(source=""),)))

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.rows[0].reasons == (REASON_INVALID_SOURCE,)


def test_unknown_source_case_insensitive_flagged_invalid_source():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(exists=True, rows=(_row(source="UnKnOwN"),))
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.rows[0].reasons == (REASON_INVALID_SOURCE,)


def test_null_fetched_at_flagged_missing_fetched_at():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(exists=True, rows=(_row(fetched_at=None),))
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.rows[0].reasons == (REASON_MISSING_FETCHED_AT,)


def test_empty_fetched_at_flagged_missing_fetched_at():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(exists=True, rows=(_row(fetched_at=""),))
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.rows[0].reasons == (REASON_MISSING_FETCHED_AT,)


def test_malformed_fetched_at_flagged_malformed_fetched_at():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(exists=True, rows=(_row(fetched_at="not-a-date"),))
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.rows[0].reasons == (REASON_MALFORMED_FETCHED_AT,)


def test_all_metrics_null_flagged_all_metrics_null():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(
            exists=True,
            rows=(
                _row(
                    avg_return_pct=None,
                    win_rate_pct=None,
                    positive_years=None,
                    total_years=None,
                    back_years=None,
                ),
            ),
        )
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.rows[0].reasons == (REASON_ALL_METRICS_NULL,)


def test_row_with_one_null_metric_is_not_flagged():
    """A row with valid source/fetched_at and at least one metric present
    must not appear in the cleanup plan — only ALL metrics null qualifies."""
    reader = _FakeReader(
        RawSeasonalityCacheObservation(
            exists=True,
            rows=(_row(win_rate_pct=None),),
        )
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.status == "PASS"
    assert response.rows == ()


def test_row_with_multiple_issues_includes_all_reasons():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(
            exists=True,
            rows=(
                _row(
                    source="unknown",
                    fetched_at=None,
                    avg_return_pct=None,
                    win_rate_pct=None,
                    positive_years=None,
                    total_years=None,
                    back_years=None,
                ),
            ),
        )
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.invalid_row_count == 1
    reasons = set(response.rows[0].reasons)
    assert reasons == {
        REASON_INVALID_SOURCE,
        REASON_MISSING_FETCHED_AT,
        REASON_ALL_METRICS_NULL,
    }


def test_invalid_reason_counts_tally_across_rows():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(
            exists=True,
            rows=(
                _row(source=None),
                _row(fetched_at=None, ticker="BBRI"),
                _row(source="unknown", ticker="TLKM"),
            ),
        )
    )

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.invalid_row_count == 3
    assert response.invalid_reason_counts[REASON_INVALID_SOURCE] == 2
    assert response.invalid_reason_counts[REASON_MISSING_FETCHED_AT] == 1
    assert response.invalid_reason_counts[REASON_MALFORMED_FETCHED_AT] == 0
    assert response.invalid_reason_counts[REASON_ALL_METRICS_NULL] == 0


def test_missing_database_returns_fail_with_source_unavailable(tmp_path: Path):
    """A wrong --db path (or genuinely missing database) must never report
    PASS — that would look identical to "checked and found nothing wrong"."""
    reader = SQLiteSeasonalityCleanupPlanReader(tmp_path / "does_not_exist.db")

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.invalid_row_count == 0
    assert response.rows == ()
    assert response.invalid_reason_counts[REASON_SEASONALITY_CACHE_UNAVAILABLE] == 1


def test_missing_table_returns_fail_with_source_unavailable(tmp_path: Path):
    """Database file exists but seasonality_cache table itself is missing —
    same fail-closed treatment as a missing database file."""
    db_path = tmp_path / "data.db"
    sqlite3.connect(str(db_path)).close()  # file exists, no tables at all
    reader = SQLiteSeasonalityCleanupPlanReader(db_path)

    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.invalid_row_count == 0
    assert response.invalid_reason_counts[REASON_SEASONALITY_CACHE_UNAVAILABLE] == 1


# ── Integration: real SQLite reader against the real production schema ──────


def test_real_reader_detects_all_reason_codes_end_to_end(tmp_path: Path):
    db_path = tmp_path / "data.db"
    StockbitSeasonalityProvider(api_client=None, db_path=db_path)  # builds schema

    with sqlite3.connect(str(db_path)) as conn:
        rows = [
            # valid
            ("BBCA", 2026, 1, 1.0, 60.0, 3, 5, 5, "stockbit", "2026-01", "2026-01-01T00:00:00"),
            # null source
            ("BBRI", 2026, 2, 1.0, 60.0, 3, 5, 5, None, "2026-02", "2026-02-01T00:00:00"),
            # empty source
            ("TLKM", 2026, 3, 1.0, 60.0, 3, 5, 5, "", "2026-03", "2026-03-01T00:00:00"),
            # unknown source (mixed case)
            ("ASII", 2026, 4, 1.0, 60.0, 3, 5, 5, "Unknown", "2026-04", "2026-04-01T00:00:00"),
            # null fetched_at
            ("UNVR", 2026, 5, 1.0, 60.0, 3, 5, 5, "stockbit", "2026-05", None),
            # malformed fetched_at
            ("ICBP", 2026, 6, 1.0, 60.0, 3, 5, 5, "stockbit", "2026-06", "not-a-date"),
            # all metrics null
            ("KLBF", 2026, 7, None, None, None, None, None, "stockbit", "2026-07", "2026-07-01T00:00:00"),
        ]
        conn.executemany(
            """
            INSERT INTO seasonality_cache
                (ticker, year, month, avg_return_pct, win_rate_pct,
                 positive_years, total_years, back_years, source, fetched_month, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    reader = SQLiteSeasonalityCleanupPlanReader(db_path)
    response = BuildSeasonalityCleanupPlanUseCase(reader=reader, clock=_clock).execute()

    assert response.status == "FAIL"
    assert response.invalid_row_count == 6
    by_ticker = {row.ticker: row.reasons for row in response.rows}
    assert "BBCA" not in by_ticker
    assert by_ticker["BBRI"] == (REASON_INVALID_SOURCE,)
    assert by_ticker["TLKM"] == (REASON_INVALID_SOURCE,)
    assert by_ticker["ASII"] == (REASON_INVALID_SOURCE,)
    assert by_ticker["UNVR"] == (REASON_MISSING_FETCHED_AT,)
    assert by_ticker["ICBP"] == (REASON_MALFORMED_FETCHED_AT,)
    assert by_ticker["KLBF"] == (REASON_ALL_METRICS_NULL,)
