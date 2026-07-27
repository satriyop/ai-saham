"""Tests for the authoritative pre-open observation capture boundary."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from src.application.services.pre_open_screen_config import PreOpenScreenConfig
from src.application.use_case.pre_open_workflow_use_case import PreOpenWorkflowRequest
from src.application.use_case.record_pre_open_observations_use_case import (
    RecordPreOpenObservationsUseCase,
)


def _request() -> PreOpenWorkflowRequest:
    return PreOpenWorkflowRequest(
        config=PreOpenScreenConfig(),
        run_date=date(2026, 6, 18),
    )


@pytest.mark.parametrize(
    (
        "collection_started_at",
        "decision_at",
        "capture_phase",
        "source_is_live",
        "snapshot_ref",
    ),
    [
        (
            datetime(2026, 6, 18, 8, 55, tzinfo=ZoneInfo("Asia/Jakarta")),
            datetime(2026, 6, 18, 8, 55, tzinfo=ZoneInfo("Asia/Jakarta")),
            "PRE_NCP",
            True,
            "test:pre-ncp",
        ),
        (
            datetime(2026, 6, 18, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta")),
            None,
            "NCP_LOCKED",
            True,
            "test:missing-time",
        ),
        (
            datetime(2026, 6, 19, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta")),
            datetime(2026, 6, 19, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
            "NCP_LOCKED",
            True,
            "test:wrong-session",
        ),
        (
            datetime(2026, 6, 18, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta")),
            datetime(2026, 6, 18, 8, 58, tzinfo=ZoneInfo("Asia/Jakarta")),
            "PRE_OPEN_MATCHING",
            True,
            "test:matching",
        ),
        (
            datetime(2026, 6, 18, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta")),
            datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
            "NCP_LOCKED",
            False,
            "test:manual-json",
        ),
    ],
)
def test_capture_rejects_unproven_ncp_before_persistence(
    collection_started_at,
    decision_at,
    capture_phase,
    source_is_live,
    snapshot_ref,
):
    workflow_request = _request()
    workflow = MagicMock()
    workflow.execute.return_value = SimpleNamespace(
        collection_started_at=collection_started_at,
        decision_at=decision_at,
        capture_phase=capture_phase,
        source_is_live=source_is_live,
        decision_snapshot_ref=snapshot_ref,
        result=SimpleNamespace(screened_date=date(2026, 6, 18)),
    )
    persister = MagicMock()
    use_case = RecordPreOpenObservationsUseCase(workflow, persister)

    with pytest.raises(ValueError, match="collection window wholly"):
        use_case.execute(workflow_request)

    workflow.execute.assert_called_once_with(workflow_request)
    persister.persist.assert_not_called()


def test_capture_accepts_proven_same_session_ncp():
    workflow = MagicMock()
    response = SimpleNamespace(
        collection_started_at=datetime(2026, 6, 18, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta")),
        decision_at=datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")),
        capture_phase="NCP_LOCKED",
        source_is_live=True,
        decision_snapshot_ref="test:ncp",
        result=SimpleNamespace(screened_date=date(2026, 6, 18)),
    )
    workflow.execute.return_value = response
    persister = MagicMock()
    from src.application.services.pre_open_observation_persister import (
        PreOpenPersistedObservation,
        PreOpenPersistResult,
    )

    persister.persist.return_value = PreOpenPersistResult(
        recorded_count=2,
        observations=(
            PreOpenPersistedObservation(
                observation_id="obs-1",
                ticker="BBCA",
                screen_result="pass",
                inserted=True,
            ),
            PreOpenPersistedObservation(
                observation_id="obs-2",
                ticker="BBRI",
                screen_result="pass",
                inserted=True,
            ),
        ),
    )
    use_case = RecordPreOpenObservationsUseCase(workflow, persister)
    workflow_request = _request()

    result = use_case.execute(workflow_request)

    assert result.response is response
    assert result.recorded_count == 2
    assert result.observations[0].observation_id == "obs-1"
    workflow.execute.assert_called_once_with(workflow_request)
    persister.persist.assert_called_once_with(response, workflow_request)
