"""Tests for ledger-backed setup phase history load/record helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from src.application.services.setup_phase_history import (
    CANONICAL_PHASE_LEDGER_WINDOW,
    build_setup_phase_history_index,
    load_previous_setup_phases,
    record_setup_phase_for_screen,
)
from src.domain.ports.setup_phase_history_repository import (
    SOURCE_WORKFLOW_SCREEN_ACCUM,
    SetupPhaseRecordResult,
)
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.persistence.sqlite_setup_phase_ledger_repository import (
    SQLiteSetupPhaseLedgerRepository,
)


def test_load_previous_phases_family_and_generic(tmp_path: Path) -> None:
    repo = SQLiteSetupPhaseLedgerRepository(tmp_path / "h.db")
    repo.record_phase(
        ticker="BBCA",
        as_of_date=date(2026, 7, 1),
        phase=SetupPhaseState.ACCUMULATION,
        setup_family="foreign-bounce",
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    repo.record_phase(
        ticker="BBCA",
        as_of_date=date(2026, 7, 2),
        phase=SetupPhaseState.COMPRESSION,
        setup_family=None,  # generic
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    repo.record_phase(
        ticker="BBCA",
        as_of_date=date(2026, 7, 3),
        phase=SetupPhaseState.BREAKOUT_CONFIRMATION,
        setup_family="breakout",
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )

    phases = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 10),
        setup_family="foreign-bounce",
    )
    assert phases == (
        SetupPhaseState.ACCUMULATION,
        SetupPhaseState.COMPRESSION,  # generic allowed for foreign-bounce
    )

    breakout_phases = load_previous_setup_phases(
        repo,
        ticker="BBCA",
        before_date=date(2026, 7, 10),
        setup_family="breakout",
    )
    # generic COMPRESSION allowed; ACCUMULATION under foreign-bounce not
    assert SetupPhaseState.COMPRESSION in breakout_phases
    assert SetupPhaseState.BREAKOUT_CONFIRMATION in breakout_phases
    assert SetupPhaseState.ACCUMULATION not in breakout_phases


def test_batch_index_and_canonical_window_write(tmp_path: Path) -> None:
    repo = SQLiteSetupPhaseLedgerRepository(tmp_path / "b.db")
    repo.record_phase(
        ticker="BBCA",
        as_of_date=date(2026, 7, 1),
        phase=SetupPhaseState.ACCUMULATION,
        setup_family="accumulation",
        source_workflow=SOURCE_WORKFLOW_SCREEN_ACCUM,
    )
    index = build_setup_phase_history_index(
        repo, tickers=["BBCA", "TLKM"], before_date=date(2026, 7, 5)
    )
    phases = load_previous_setup_phases(
        None,
        ticker="BBCA",
        before_date=date(2026, 7, 5),
        setup_family="accumulation",
        history_index=index,
    )
    assert phases == (SetupPhaseState.ACCUMULATION,)

    assert (
        record_setup_phase_for_screen(
            repo,
            ticker="BBCA",
            as_of_date=date(2026, 7, 5),
            phase=SetupPhaseState.COMPRESSION,
            setup_family="accumulation",
            window_days=30,
        )
        is SetupPhaseRecordResult.SKIPPED_POLICY
    )
    assert (
        record_setup_phase_for_screen(
            repo,
            ticker="BBCA",
            as_of_date=date(2026, 7, 5),
            phase=SetupPhaseState.COMPRESSION,
            setup_family="accumulation",
            window_days=CANONICAL_PHASE_LEDGER_WINDOW,
        )
        is SetupPhaseRecordResult.INSERTED
    )
