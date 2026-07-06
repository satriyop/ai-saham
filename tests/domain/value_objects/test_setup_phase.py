from datetime import date

import pytest

from src.domain.value_objects.setup_phase import (
    SetupPhaseHistoryEntry,
    SetupPhaseSnapshot,
    SetupPhaseState,
)


def test_setup_phase_snapshot_serializes_round_trip():
    snapshot = SetupPhaseSnapshot(
        current_phase=SetupPhaseState.COMPRESSION,
        previous_phase=SetupPhaseState.ACCUMULATION,
        phase_age_sessions=3,
        phase_strength=0.7,
        coverage_score=0.8,
        conviction_score=0.56,
        sequence_valid=True,
        reasons=("compression: BB width readiness",),
        unavailable_evidence_reasons=("volume unavailable",),
        history=(
            SetupPhaseHistoryEntry(
                phase=SetupPhaseState.ACCUMULATION,
                started_at=date(2026, 6, 1),
                ended_at=date(2026, 6, 5),
                age_sessions=4,
                strength=0.6,
                reasons=("flow present",),
                sequence_valid_after_transition=True,
            ),
        ),
    )

    parsed = SetupPhaseSnapshot.from_dict(snapshot.to_dict())

    assert parsed == snapshot


def test_setup_phase_snapshot_validates_score_bounds():
    with pytest.raises(ValueError, match="coverage_score"):
        SetupPhaseSnapshot(
            current_phase=SetupPhaseState.NONE,
            previous_phase=None,
            phase_age_sessions=0,
            phase_strength=0.0,
            coverage_score=1.1,
            conviction_score=0.0,
            sequence_valid=None,
        )


def test_setup_phase_history_validates_age():
    with pytest.raises(ValueError, match="age_sessions"):
        SetupPhaseHistoryEntry(
            phase=SetupPhaseState.FAILED,
            started_at=None,
            ended_at=None,
            age_sessions=-1,
            strength=0.2,
        )
