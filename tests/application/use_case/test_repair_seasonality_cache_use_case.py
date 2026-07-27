"""Tests for RepairSeasonalityCacheUseCase (DQ-001H)."""

from __future__ import annotations

from src.application.use_case.build_seasonality_cleanup_plan_use_case import (
    REASON_ALL_METRICS_NULL,
    REASON_DATABASE_MISSING,
    REASON_INVALID_SOURCE,
    REASON_MALFORMED_FETCHED_AT,
    REASON_MISSING_FETCHED_AT,
    REASON_SEASONALITY_CACHE_TABLE_MISSING,
    RawSeasonalityCacheObservation,
    RawSeasonalityCacheRow,
)
from src.application.use_case.repair_seasonality_cache_use_case import (
    RepairSeasonalityCacheUseCase,
    SeasonalityCacheRepairRow,
)


class _FakeReader:
    """Fake SeasonalityCleanupPlanReader for testing."""

    def __init__(
        self,
        observation: RawSeasonalityCacheObservation,
        exists: bool = True,
    ) -> None:
        self._observation = observation
        self._exists = exists

    def database_exists(self) -> bool:
        return self._exists

    def observe_seasonality_cache(self) -> RawSeasonalityCacheObservation:
        return self._observation


class _FakeRepairer:
    """Fake SeasonalityCacheRepairer that records calls."""

    def __init__(self) -> None:
        self.ensure_called = False
        self.quarantine_calls: list[tuple[list[SeasonalityCacheRepairRow], str]] = []

    def ensure_quarantine_table(self) -> None:
        self.ensure_called = True

    def quarantine_and_delete(
        self,
        rows: list[SeasonalityCacheRepairRow],
        repair_run_id: str,
    ) -> int:
        self.quarantine_calls.append((rows, repair_run_id))
        return len(rows)


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


# ── Dry-run tests ────────────────────────────────────────────────────────────


def test_dry_run_reports_invalid_rows_and_does_not_call_repairer():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(source=None),)))
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=True)

    assert response.status == "FAIL"
    assert response.dry_run is True
    assert response.mode == "DRY_RUN"
    assert response.invalid_row_count == 1
    assert response.quarantined_row_count == 0
    assert response.deleted_row_count == 0
    assert response.artifact_type == "seasonality_cache_repair"
    assert response.schema_version == 1
    assert repairer.ensure_called is False
    assert repairer.quarantine_calls == []


def test_dry_run_is_default():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(source=None),)))
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute()

    assert response.dry_run is True
    assert response.mode == "DRY_RUN"


def test_dry_run_lists_rows_with_reasons():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(
            exists=True,
            rows=(
                _row(source=None, ticker="BBRI"),
                _row(fetched_at="not-a-date", ticker="TLKM"),
            ),
        )
    )
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=True)

    assert response.invalid_row_count == 2
    assert len(response.rows) == 2
    by_ticker = {r.ticker: r for r in response.rows}
    assert by_ticker["BBRI"].reasons == (REASON_INVALID_SOURCE,)
    assert by_ticker["TLKM"].reasons == (REASON_MALFORMED_FETCHED_AT,)


# ── Apply tests ──────────────────────────────────────────────────────────────


def test_apply_calls_quarantine_and_delete_with_invalid_rows():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(
            exists=True,
            rows=(_row(source=None), _row(fetched_at="", ticker="BBRI")),
        )
    )
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=False)

    assert response.status == "PASS"
    assert response.dry_run is False
    assert response.mode == "APPLY"
    assert response.invalid_row_count == 2
    assert response.quarantined_row_count == 2
    assert response.deleted_row_count == 2
    assert repairer.ensure_called is True
    assert len(repairer.quarantine_calls) == 1
    rows_arg, run_id = repairer.quarantine_calls[0]
    assert len(rows_arg) == 2
    assert rows_arg[0].ticker == "BBCA"
    assert rows_arg[1].ticker == "BBRI"
    assert isinstance(run_id, str) and len(run_id) > 10


def test_apply_reuses_repair_run_id_in_response():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(source=None),)))
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=False)

    rows_arg, run_id = repairer.quarantine_calls[0]
    assert response.repair_run_id == run_id


# ── Missing source tests ─────────────────────────────────────────────────────


def test_missing_database_returns_fail_no_mutation():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(exists=False),
        exists=False,
    )
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=False)

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.source_unavailable_reason == REASON_DATABASE_MISSING
    assert response.invalid_row_count == 0
    assert response.quarantined_row_count == 0
    assert response.dry_run is False  # preserves requested mode
    assert repairer.ensure_called is False
    assert repairer.quarantine_calls == []
    assert response.mode == "APPLY"  # mode reflects requested mode, not dry_run fallback


def test_missing_table_returns_fail_no_mutation():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(exists=False),
        exists=True,
    )
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=False)

    assert response.status == "FAIL"
    assert response.source_available is False
    assert response.source_unavailable_reason == REASON_SEASONALITY_CACHE_TABLE_MISSING
    assert response.invalid_row_count == 0
    assert repairer.quarantine_calls == []


# ── No invalid rows tests ────────────────────────────────────────────────────


def test_no_invalid_rows_returns_pass():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(),)))
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=False)

    assert response.status == "PASS"
    assert response.source_available is True
    assert response.invalid_row_count == 0
    assert response.quarantined_row_count == 0
    assert response.deleted_row_count == 0
    assert repairer.quarantine_calls == []


def test_no_invalid_rows_dry_run_also_returns_pass():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(),)))
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=True)

    assert response.status == "PASS"
    assert response.dry_run is True


# ── Reason counts tests ──────────────────────────────────────────────────────


def test_reason_counts_tally_across_rows():
    reader = _FakeReader(
        RawSeasonalityCacheObservation(
            exists=True,
            rows=(
                _row(source=None),  # INVALID_SOURCE
                _row(fetched_at=None, ticker="BBRI"),  # MISSING_FETCHED_AT + INVALID_SOURCE
                _row(
                    source="unknown",
                    fetched_at=None,
                    avg_return_pct=None,
                    win_rate_pct=None,
                    positive_years=None,
                    total_years=None,
                    back_years=None,
                    ticker="TLKM",
                ),
            ),
        )
    )
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=True)

    assert response.invalid_row_count == 3
    assert response.reason_counts[REASON_INVALID_SOURCE] == 2  # rows 1 (None) + 3 ("unknown")
    assert response.reason_counts[REASON_MISSING_FETCHED_AT] == 2
    assert response.reason_counts[REASON_ALL_METRICS_NULL] == 1
    assert response.reason_counts[REASON_MALFORMED_FETCHED_AT] == 0


# ── Response shape tests ─────────────────────────────────────────────────────


def test_response_to_dict_includes_all_required_keys():
    reader = _FakeReader(RawSeasonalityCacheObservation(exists=True, rows=(_row(source=None),)))
    repairer = _FakeRepairer()

    response = RepairSeasonalityCacheUseCase(
        reader=reader, repairer=repairer, clock=_clock
    ).execute(dry_run=True)
    data = response.to_dict()

    assert data["artifact_type"] == "seasonality_cache_repair"
    assert data["schema_version"] == 1
    assert data["mode"] == "DRY_RUN"
    assert data["status"] == "FAIL"
    assert data["source_available"] is True
    assert data["invalid_row_count"] == 1
    assert data["quarantined_row_count"] == 0
    assert data["deleted_row_count"] == 0
    assert data["dry_run"] is True
    assert isinstance(data["repair_run_id"], str)
    assert "reason_counts" in data
    assert len(data["rows"]) == 1
    assert data["rows"][0]["ticker"] == "BBCA"
    assert data["rows"][0]["reasons"] == [REASON_INVALID_SOURCE]
