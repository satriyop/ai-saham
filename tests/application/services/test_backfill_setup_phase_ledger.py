"""Backfill setup phase ledger from observation-like payloads."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from src.application.services.backfill_setup_phase_ledger import (
    backfill_setup_phase_ledger_from_observations,
)
from src.domain.value_objects.learning_artifacts import AssessmentPurpose
from src.domain.value_objects.setup_phase import SetupPhaseState
from src.infrastructure.persistence.sqlite_setup_phase_ledger_repository import (
    SQLiteSetupPhaseLedgerRepository,
)


class _FakeObsRepo:
    def __init__(self, observations: list) -> None:
        self._observations = observations

    def list_observations(self, purpose, *, compatibility_id=None):
        assert purpose is AssessmentPurpose.ACCUMULATION_DISCOVERY
        return list(self._observations)


def test_backfill_prefers_window_7(tmp_path: Path) -> None:
    ledger = SQLiteSetupPhaseLedgerRepository(tmp_path / "bf.db")
    obs = SimpleNamespace(
        observation_id="obs-1",
        cutoff_at=datetime(2026, 7, 10, 16, 0, tzinfo=timezone.utc),
        decision_payload={
            "ticker": "BBCA",
            "workflow": "research_accum_capture",
            "features_by_window": {
                "7": {
                    "ticker": "BBCA",
                    "snapshot_date": "2026-07-10",
                    "workflow": "screen_accum",
                    "sub_signal_fingerprint": {
                        "setup_phase_current": "COMPRESSION",
                        "primary_setup_family": "foreign-bounce",
                    },
                },
                "30": {
                    "ticker": "BBCA",
                    "snapshot_date": "2026-07-10",
                    "sub_signal_fingerprint": {
                        "setup_phase_current": "DISTRIBUTION",
                    },
                },
            },
        },
    )
    report = backfill_setup_phase_ledger_from_observations(
        observation_repository=_FakeObsRepo([obs]),
        ledger_repository=ledger,
    )
    assert report.rows_written == 1
    rows = ledger.list_rows_before(ticker="BBCA", before_date=date(2026, 7, 11))
    assert len(rows) == 1
    assert rows[0].phase is SetupPhaseState.COMPRESSION
    assert rows[0].setup_family == "foreign-bounce"
