"""Unit tests for setup phase ledger SQLite repository."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.domain.ports.setup_phase_history_repository import (
    SOURCE_WORKFLOW_SCREEN_ACCUM,
    SetupPhaseRecordResult,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.persistence.sqlite_setup_phase_ledger_repository import (
    SQLiteSetupPhaseLedgerRepository,
)


def test_record_insert_update_and_list(tmp_path: Path) -> None:
    repo = SQLiteSetupPhaseLedgerRepository(tmp_path / "t.db")
    r1 = repo.record_phase(
        ticker="bbca",
        as_of_date=date(2026, 7, 20),
        phase=SetupPhaseState.ACCUMULATION,
        setup_family="foreign-bounce",
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    assert r1 is SetupPhaseRecordResult.INSERTED

    r2 = repo.record_phase(
        ticker="BBCA",
        as_of_date=date(2026, 7, 20),
        phase=SetupPhaseState.ACCUMULATION,
        setup_family="foreign-bounce",
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    assert r2 is SetupPhaseRecordResult.SKIPPED_IDENTICAL

    r3 = repo.record_phase(
        ticker="BBCA",
        as_of_date=date(2026, 7, 20),
        phase=SetupPhaseState.COMPRESSION,
        setup_family="foreign-bounce",
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    assert r3 is SetupPhaseRecordResult.UPDATED

    rows = repo.list_rows_before(ticker="BBCA", before_date=date(2026, 7, 21))
    assert len(rows) == 1
    assert rows[0].phase is SetupPhaseState.COMPRESSION

    empty = repo.list_rows_before(ticker="BBCA", before_date=date(2026, 7, 20))
    assert empty == ()


def test_list_rows_before_many_and_skip_none(tmp_path: Path) -> None:
    repo = SQLiteSetupPhaseLedgerRepository(tmp_path / "t2.db")
    assert (
        repo.record_phase(
            ticker="BBCA",
            as_of_date=date(2026, 7, 10),
            phase=SetupPhaseState.NONE,
            setup_family=None,
            source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
        )
        is SetupPhaseRecordResult.SKIPPED_POLICY
    )
    repo.record_phase(
        ticker="BBCA",
        as_of_date=date(2026, 7, 10),
        phase=SetupPhaseState.COMPRESSION,
        setup_family=None,
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    repo.record_phase(
        ticker="BBRI",
        as_of_date=date(2026, 7, 11),
        phase=SetupPhaseState.ACCUMULATION,
        setup_family="accumulation",
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    many = repo.list_rows_before_many(
        tickers=["BBCA", "BBRI", "TLKM"],
        before_date=date(2026, 7, 20),
    )
    assert {r.ticker for r in many} == {"BBCA", "BBRI"}
