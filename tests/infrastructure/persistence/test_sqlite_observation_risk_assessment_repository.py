"""Tests for SQLiteObservationRiskAssessmentRepository."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.domain.ports.observation_risk_assessment_repository import (
    ObservationRiskAssessmentRecord,
)
from src.infrastructure.persistence.sqlite_observation_risk_assessment_repository import (
    SQLiteObservationRiskAssessmentRepository,
)


def _record(
    *,
    gate_triggered: str | None = "LiquidityGate",
    setup_action: str | None = "WATCH",
    assessed_at: datetime | None = None,
) -> ObservationRiskAssessmentRecord:
    return ObservationRiskAssessmentRecord(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 16),
        workflow="screen_accum",
        window_sessions=7,
        data_as_of_date=date(2026, 7, 15),
        config_hash="abc123",
        assessed_at=assessed_at or datetime(2026, 7, 16, 15, 0, 0),
        schema_version=1,
        risk_assessment_json={
            "snapshot_date": "2026-07-16",
            "gate_triggered": gate_triggered,
            "confidence": 80,
            "rationale": ["blocked"],
            "indicators": {"date": "2026-07-16", "sma": "100", "ema": "101", "rsi": "50", "extras": []},
        },
        trade_setup_json={"action": setup_action, "ticker": "BBCA"},
        gate_triggered=gate_triggered,
        setup_action=setup_action,
    )


def test_save_many_upserts_by_canonical_identity(tmp_path: Path) -> None:
    repo = SQLiteObservationRiskAssessmentRepository(tmp_path / "data.db")
    first = _record(gate_triggered="LiquidityGate", setup_action="WATCH")
    second = _record(
        gate_triggered="FundamentalGate",
        setup_action="AVOID",
        assessed_at=datetime(2026, 7, 16, 16, 0, 0),
    )

    assert repo.save_many([first]) == 1
    stored = repo.get_by_identity(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 16),
        workflow="screen_accum",
        window_sessions=7,
        data_as_of_date=date(2026, 7, 15),
        config_hash="abc123",
    )
    assert stored is not None
    assert stored.gate_triggered == "LiquidityGate"
    assert stored.setup_action == "WATCH"

    assert repo.save_many([second]) == 1
    replaced = repo.get_by_identity(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 16),
        workflow="screen_accum",
        window_sessions=7,
        data_as_of_date=date(2026, 7, 15),
        config_hash="abc123",
    )
    assert replaced is not None
    assert replaced.gate_triggered == "FundamentalGate"
    assert replaced.setup_action == "AVOID"
    assert replaced.assessed_at == datetime(2026, 7, 16, 16, 0, 0)
    assert replaced.risk_assessment_json["gate_triggered"] == "FundamentalGate"


def test_repository_does_not_invent_risk_from_lean_payload_fields(tmp_path: Path) -> None:
    """Child rows require explicit RiskAssessment JSON — lean payload fields alone
    must not be synthesized into a risk assessment row."""
    repo = SQLiteObservationRiskAssessmentRepository(tmp_path / "data.db")

    stored = repo.get_by_identity(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 16),
        workflow="screen_accum",
        window_sessions=7,
        data_as_of_date=date(2026, 7, 15),
        config_hash="abc123",
    )
    assert stored is None

    assert repo.save_many([]) == 0
