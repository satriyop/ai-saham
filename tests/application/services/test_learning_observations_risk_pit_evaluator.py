"""Pure evaluator tests for learning_observations risk PIT check."""

from __future__ import annotations

from src.application.dto.source_reconciliation_dto import (
    RawLearningObservationsRiskPitObservation,
)
from src.application.services.source_reconciliation_artifact_evaluator import (
    evaluate_learning_observations_risk_pit,
)


def test_clean_raw_passes_with_zero_findings() -> None:
    check, findings = evaluate_learning_observations_risk_pit(
        RawLearningObservationsRiskPitObservation(exists=True, row_count=10)
    )
    assert check.name == "learning_observations_risk_pit"
    assert check.status == "PASS"
    assert findings == ()


def test_after_session_fails() -> None:
    samples = (
        {
            "ticker": "GOTO",
            "session_date": "2026-06-02",
            "risk_snapshot_date": "2026-07-28",
        },
    )
    check, findings = evaluate_learning_observations_risk_pit(
        RawLearningObservationsRiskPitObservation(
            exists=True,
            row_count=5,
            risk_snapshot_after_session_count=3,
            risk_snapshot_after_session_samples=samples,
        )
    )
    assert check.status == "FAIL"
    assert len(findings) == 1
    f = findings[0]
    assert f.severity == "FAIL"
    assert f.code == "LEARNING_OBSERVATIONS_RISK_SNAPSHOT_AFTER_SESSION"
    assert f.mismatch_count == 3
    assert f.sample_rows == samples


def test_sample_cap_preserved_from_raw() -> None:
    samples = tuple(
        {
            "ticker": f"T{i}",
            "session_date": "2026-06-02",
            "risk_snapshot_date": "2026-07-28",
        }
        for i in range(10)
    )
    _, findings = evaluate_learning_observations_risk_pit(
        RawLearningObservationsRiskPitObservation(
            exists=True,
            row_count=15,
            risk_snapshot_after_session_count=15,
            risk_snapshot_after_session_samples=samples,
        )
    )
    assert len(findings[0].sample_rows) == 10


def test_gate_mismatch_only_warns() -> None:
    check, findings = evaluate_learning_observations_risk_pit(
        RawLearningObservationsRiskPitObservation(
            exists=True,
            row_count=2,
            gate_context_session_mismatch_count=1,
            gate_context_session_mismatch_samples=(
                {
                    "ticker": "BBCA",
                    "session_date": "2026-06-02",
                    "gate_context_snapshot_date": "2026-06-03",
                },
            ),
        )
    )
    assert check.status == "WARN"
    assert findings[0].code == "LEARNING_OBSERVATIONS_GATE_CONTEXT_SESSION_MISMATCH"
    assert findings[0].severity == "WARN"


def test_unreadable_only_warns() -> None:
    check, findings = evaluate_learning_observations_risk_pit(
        RawLearningObservationsRiskPitObservation(
            exists=True,
            row_count=1,
            risk_snapshot_unreadable_count=1,
        )
    )
    assert check.status == "WARN"
    assert findings[0].code == "LEARNING_OBSERVATIONS_RISK_SNAPSHOT_UNREADABLE"


def test_after_and_mismatch_overall_fail() -> None:
    check, findings = evaluate_learning_observations_risk_pit(
        RawLearningObservationsRiskPitObservation(
            exists=True,
            row_count=4,
            risk_snapshot_after_session_count=2,
            gate_context_session_mismatch_count=1,
        )
    )
    assert check.status == "FAIL"
    codes = {f.code for f in findings}
    assert "LEARNING_OBSERVATIONS_RISK_SNAPSHOT_AFTER_SESSION" in codes
    assert "LEARNING_OBSERVATIONS_GATE_CONTEXT_SESSION_MISMATCH" in codes


def test_missing_table_is_warn() -> None:
    check, findings = evaluate_learning_observations_risk_pit(
        RawLearningObservationsRiskPitObservation(exists=False)
    )
    assert check.status == "WARN"
    assert findings[0].code == "MISSING_OPTIONAL_ARTIFACT_TABLE"


def test_schema_insufficient_fails() -> None:
    check, findings = evaluate_learning_observations_risk_pit(
        RawLearningObservationsRiskPitObservation(
            exists=True,
            row_count=1,
            schema_sufficient=False,
            missing_columns=("decision_payload_json",),
        )
    )
    assert check.status == "FAIL"
    assert findings[0].code == "LEARNING_OBSERVATIONS_SCHEMA_INSUFFICIENT"
