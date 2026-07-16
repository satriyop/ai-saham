"""Tests for AuditCandidateObservationIdentityUseCase (DQ-001I)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.use_case.audit_candidate_observation_identity_use_case import (
    AuditCandidateObservationIdentityUseCase,
    CandidateObservationIdentityAuditResponse,
    CandidateObservationIdentityReader,
    DATABASE_MISSING,
    CANDIDATE_OBSERVATIONS_TABLE_MISSING,
    RawCandidateObservationIdentityData,
)


def _clock() -> str:
    return "2026-07-16T00:00:00+00:00"


class _FakeReader:
    """Implements CandidateObservationIdentityReader protocol."""

    def __init__(
        self,
        data: RawCandidateObservationIdentityData | None = None,
        exists: bool = True,
    ) -> None:
        self._data = data or RawCandidateObservationIdentityData(exists=True)
        self._exists = exists

    def database_exists(self) -> bool:
        return self._exists

    def observe_candidate_observation_identity(self) -> RawCandidateObservationIdentityData:
        return self._data


def _make(data: RawCandidateObservationIdentityData | None = None, exists: bool = True):
    return AuditCandidateObservationIdentityUseCase(
        reader=_FakeReader(data=data, exists=exists),
        clock=_clock,
    )


# ── Helper for default data ──────────────────────────────────────────────────


def _all_legacy_data(
    total: int = 100,
    legacy: int | None = None,
    latest_legacy: int = 10,
    latest_total: int = 10,
    latest_date: str = "2026-07-15",
    **overrides,
) -> RawCandidateObservationIdentityData:
    """Build RawCandidateObservationIdentityData with all-legacy defaults."""
    legacy = legacy if legacy is not None else total
    canonical = total - legacy
    dep = {
        "latest_snapshot_date": latest_date,
        "latest_total_rows": latest_total,
        "latest_legacy_rows": latest_legacy,
        "latest_canonical_rows": latest_total - latest_legacy,
        "depends_on_legacy": latest_legacy > 0,
    }
    data = RawCandidateObservationIdentityData(
        exists=True,
        total_row_count=total,
        canonical_row_count=canonical,
        legacy_row_count=legacy,
        snapshot_date_min="2025-01-01",
        snapshot_date_max=latest_date,
        captured_at_min="2025-01-01T00:00:00+00:00",
        captured_at_max="2026-07-15T23:59:59+00:00",
        missing_identity_counts={
            "config_hash": legacy,
            "workflow": 0,
            "window_sessions": 0,
            "data_as_of_date": 0,
        },
        workflow_counts=[{"workflow": "accumulation_screen", "row_count": total}],
        window_session_counts=[{"window_sessions": 30, "row_count": total}],
        legacy_by_snapshot_date=[{"snapshot_date": latest_date, "row_count": legacy}],
        latest_readiness_dependency=dep,
        missing_columns=(),
    )
    return data


# ── Tests ────────────────────────────────────────────────────────────────────


class TestSourceUnavailable:
    def test_missing_database_returns_fail(self):
        use_case = _make(exists=False)
        response = use_case.execute()

        assert response.status == "FAIL"
        assert response.source_available is False
        assert response.source_unavailable_reason == DATABASE_MISSING
        assert response.recommendation == "SOURCE_UNAVAILABLE"
        assert response.total_row_count == 0
        assert len(response.findings) == 1
        assert response.findings[0]["code"] == "SOURCE_UNAVAILABLE"

    def test_missing_table_returns_fail(self):
        data = RawCandidateObservationIdentityData(exists=False)
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "FAIL"
        assert response.source_available is False
        assert response.source_unavailable_reason == CANDIDATE_OBSERVATIONS_TABLE_MISSING
        assert response.recommendation == "SOURCE_UNAVAILABLE"


class TestEmptyTable:
    def test_empty_table_returns_pass_no_action(self):
        data = RawCandidateObservationIdentityData(exists=True, total_row_count=0)
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "PASS"
        assert response.recommendation == "NO_ACTION"
        assert response.total_row_count == 0
        assert response.legacy_row_count == 0
        assert response.canonical_row_count == 0
        assert response.legacy_ratio == 0.0
        assert any(f["code"] == "NO_CANDIDATE_OBSERVATIONS" for f in response.findings)


class TestAllLegacyLatestLegacy:
    def test_all_legacy_with_latest_legacy_returns_fail_rebuild_required(self):
        data = _all_legacy_data(total=100, legacy=100, latest_legacy=10, latest_total=10)
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "FAIL"
        assert response.recommendation == "REBUILD_REQUIRED"
        assert response.total_row_count == 100
        assert response.legacy_row_count == 100
        assert response.canonical_row_count == 0
        assert response.legacy_ratio == 1.0
        assert any(
            f["code"] == "LATEST_READINESS_DEPENDS_ON_LEGACY_IDENTITY"
            for f in response.findings
        )

    def test_mixed_legacy_with_latest_legacy_returns_fail(self):
        dep = {
            "latest_snapshot_date": "2026-07-15",
            "latest_total_rows": 10,
            "latest_legacy_rows": 5,
            "latest_canonical_rows": 5,
            "depends_on_legacy": True,
        }
        data = _all_legacy_data(total=200, legacy=50, latest_legacy=5, latest_total=10)
        data = RawCandidateObservationIdentityData(
            exists=True,
            total_row_count=200,
            canonical_row_count=150,
            legacy_row_count=50,
            snapshot_date_min="2025-01-01",
            snapshot_date_max="2026-07-15",
            missing_identity_counts={
                "config_hash": 50,
                "workflow": 0,
                "window_sessions": 0,
                "data_as_of_date": 0,
            },
            workflow_counts=[{"workflow": "accumulation_screen", "row_count": 200}],
            window_session_counts=[{"window_sessions": 30, "row_count": 200}],
            legacy_by_snapshot_date=[{"snapshot_date": "2026-07-15", "row_count": 5}],
            latest_readiness_dependency=dep,
            missing_columns=(),
        )
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "FAIL"
        assert response.recommendation == "REBUILD_REQUIRED"
        assert response.legacy_row_count == 50
        assert response.canonical_row_count == 150
        assert response.legacy_ratio == 0.25


class TestHistoricalLegacyLatestCanonical:
    def test_historical_legacy_latest_canonical_returns_warn_quarantine_safe(self):
        dep = {
            "latest_snapshot_date": "2026-07-15",
            "latest_total_rows": 10,
            "latest_legacy_rows": 0,
            "latest_canonical_rows": 10,
            "depends_on_legacy": False,
        }
        data = RawCandidateObservationIdentityData(
            exists=True,
            total_row_count=200,
            canonical_row_count=150,
            legacy_row_count=50,
            snapshot_date_min="2025-01-01",
            snapshot_date_max="2026-07-15",
            captured_at_min="2025-01-01T00:00:00+00:00",
            captured_at_max="2026-07-15T23:59:59+00:00",
            missing_identity_counts={
                "config_hash": 50,
                "workflow": 0,
                "window_sessions": 0,
                "data_as_of_date": 0,
            },
            workflow_counts=[{"workflow": "accumulation_screen", "row_count": 200}],
            window_session_counts=[{"window_sessions": 30, "row_count": 200}],
            legacy_by_snapshot_date=[{"snapshot_date": "2025-06-01", "row_count": 50}],
            latest_readiness_dependency=dep,
            missing_columns=(),
        )
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "WARN"
        assert response.recommendation == "QUARANTINE_SAFE"
        assert any(f["code"] == "HISTORICAL_LEGACY_ROWS_PRESENT" for f in response.findings)


class TestAllCanonicalClean:
    def test_all_canonical_no_duplicates_returns_pass_no_action(self):
        dep = {
            "latest_snapshot_date": "2026-07-15",
            "latest_total_rows": 10,
            "latest_legacy_rows": 0,
            "latest_canonical_rows": 10,
            "depends_on_legacy": False,
        }
        data = RawCandidateObservationIdentityData(
            exists=True,
            total_row_count=200,
            canonical_row_count=200,
            legacy_row_count=0,
            snapshot_date_min="2025-01-01",
            snapshot_date_max="2026-07-15",
            captured_at_min="2025-01-01T00:00:00+00:00",
            captured_at_max="2026-07-15T23:59:59+00:00",
            missing_identity_counts={
                "config_hash": 0,
                "workflow": 0,
                "window_sessions": 0,
                "data_as_of_date": 0,
            },
            workflow_counts=[{"workflow": "accumulation_screen", "row_count": 200}],
            window_session_counts=[{"window_sessions": 30, "row_count": 200}],
            legacy_by_snapshot_date=[],
            latest_readiness_dependency=dep,
            missing_columns=(),
        )
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "PASS"
        assert response.recommendation == "NO_ACTION"
        assert response.canonical_row_count == 200
        assert response.legacy_row_count == 0


class TestDuplicateCanonicalIdentity:
    def test_duplicates_with_all_canonical_returns_warn(self):
        dep = {
            "latest_snapshot_date": "2026-07-15",
            "latest_total_rows": 10,
            "latest_legacy_rows": 0,
            "latest_canonical_rows": 10,
            "depends_on_legacy": False,
        }
        data = RawCandidateObservationIdentityData(
            exists=True,
            total_row_count=200,
            canonical_row_count=200,
            legacy_row_count=0,
            snapshot_date_min="2025-01-01",
            snapshot_date_max="2026-07-15",
            missing_identity_counts={
                "config_hash": 0,
                "workflow": 0,
                "window_sessions": 0,
                "data_as_of_date": 0,
            },
            workflow_counts=[{"workflow": "accumulation_screen", "row_count": 200}],
            window_session_counts=[{"window_sessions": 30, "row_count": 200}],
            legacy_by_snapshot_date=[],
            latest_readiness_dependency=dep,
            duplicate_identity_group_count=3,
            duplicate_identity_row_count=8,
            missing_columns=(),
        )
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "WARN"
        assert response.duplicate_identity_group_count == 3
        assert response.duplicate_identity_row_count == 8
        assert any(f["code"] == "DUPLICATE_CANONICAL_IDENTITY_GROUPS" for f in response.findings)

    def test_duplicates_with_legacy_latest_also_reports_warn_duplicate(self):
        dep = {
            "latest_snapshot_date": "2026-07-15",
            "latest_total_rows": 10,
            "latest_legacy_rows": 5,
            "latest_canonical_rows": 5,
            "depends_on_legacy": True,
        }
        data = RawCandidateObservationIdentityData(
            exists=True,
            total_row_count=200,
            canonical_row_count=190,
            legacy_row_count=10,
            snapshot_date_min="2025-01-01",
            snapshot_date_max="2026-07-15",
            missing_identity_counts={
                "config_hash": 10,
                "workflow": 0,
                "window_sessions": 0,
                "data_as_of_date": 0,
            },
            workflow_counts=[{"workflow": "accumulation_screen", "row_count": 200}],
            window_session_counts=[{"window_sessions": 30, "row_count": 200}],
            legacy_by_snapshot_date=[{"snapshot_date": "2026-07-15", "row_count": 5}],
            latest_readiness_dependency=dep,
            duplicate_identity_group_count=2,
            duplicate_identity_row_count=6,
            missing_columns=(),
        )
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "FAIL"
        assert response.recommendation == "REBUILD_REQUIRED"
        assert any(
            f["code"] == "LATEST_READINESS_DEPENDS_ON_LEGACY_IDENTITY"
            for f in response.findings
        )
        assert any(f["code"] == "DUPLICATE_CANONICAL_IDENTITY_GROUPS" for f in response.findings)


class TestMissingColumn:
    def test_missing_column_creates_warn_finding(self):
        dep = {
            "latest_snapshot_date": "2026-07-15",
            "latest_total_rows": 10,
            "latest_legacy_rows": 0,
            "latest_canonical_rows": 10,
            "depends_on_legacy": False,
        }
        data = RawCandidateObservationIdentityData(
            exists=True,
            total_row_count=200,
            canonical_row_count=200,
            legacy_row_count=0,
            snapshot_date_min="2025-01-01",
            snapshot_date_max="2026-07-15",
            missing_identity_counts={
                "config_hash": 0,
                "workflow": 200,
                "window_sessions": 0,
                "data_as_of_date": 0,
            },
            workflow_counts=[{"workflow": "(unknown)", "row_count": 200}],
            window_session_counts=[{"window_sessions": 30, "row_count": 200}],
            legacy_by_snapshot_date=[],
            latest_readiness_dependency=dep,
            missing_columns=("workflow",),
        )
        use_case = _make(data=data)
        response = use_case.execute()

        assert response.status == "WARN"
        assert any(f["code"] == "IDENTITY_COLUMN_MISSING" for f in response.findings)
        assert response.missing_identity_counts["workflow"] == 200


class TestResponseShape:
    def test_to_dict_includes_all_required_keys(self):
        data = _all_legacy_data()
        use_case = _make(data=data)
        response = use_case.execute()
        d = response.to_dict()

        assert d["artifact_type"] == "candidate_observation_identity_audit"
        assert d["schema_version"] == 1
        assert d["table"] == "candidate_observations"
        assert d["status"] == "FAIL"
        assert d["source_available"] is True
        assert d["source_unavailable_reason"] is None
        assert d["total_row_count"] == 100
        assert d["canonical_row_count"] == 0
        assert d["legacy_row_count"] == 100
        assert isinstance(d["legacy_ratio"], float)
        assert d["snapshot_date_min"] is not None
        assert d["snapshot_date_max"] is not None
        assert d["captured_at_min"] is not None
        assert d["captured_at_max"] is not None
        assert isinstance(d["missing_identity_counts"], dict)
        assert isinstance(d["workflow_counts"], list)
        assert isinstance(d["window_session_counts"], list)
        assert isinstance(d["legacy_by_snapshot_date"], list)
        assert isinstance(d["duplicate_identity_group_count"], int)
        assert isinstance(d["duplicate_identity_row_count"], int)
        assert isinstance(d["latest_readiness_dependency"], dict)
        assert d["recommendation"] == "REBUILD_REQUIRED"
        assert isinstance(d["findings"], list)
        assert len(d["findings"]) > 0
