"""Unit tests for application-owned pre-open JSON payload builders."""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.application.dto.screen_contract import ScreenResultStatus
from src.application.dto.screen_pre_open_payload import (
    build_pre_open_envelope,
    build_pre_open_failure_envelope,
    default_pre_open_fetch_hint,
    resolve_pre_open_result_status,
)
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenDataFreshness,
    PreOpenWorkflowResponse,
)
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
from src.domain.value_objects.screener_result import (
    PreOpenScreenResult,
    ScreenerCandidate,
)


def _candidate(ticker: str = "BBCA") -> ScreenerCandidate:
    return ScreenerCandidate(
        ticker=ticker,
        iev=150_000,
        entry_price=Decimal("1000"),
        stop_loss_price=Decimal("950"),
        capital=Decimal("3000000"),
    )


def _response(
    *,
    candidates: list[ScreenerCandidate],
    source_status: PreOpenSourceStatus = PreOpenSourceStatus.LIVE_SUCCESS,
    source_message: str | None = None,
) -> PreOpenWorkflowResponse:
    return PreOpenWorkflowResponse(
        result=PreOpenScreenResult(
            screened_date=date(2026, 6, 12),
            iev_min=100_000,
            total_movers_seen=max(len(candidates), 1),
            candidates=candidates,
        ),
        warnings=["warn"],
        raw_movers=[],
        data_freshness=PreOpenDataFreshness(
            analysis_date=date(2026, 6, 12),
            candle_end=date(2026, 6, 11),
            broker_end=date(2026, 6, 10),
        ),
        source_status=source_status,
        source_message=source_message,
        source_is_live=True,
        ncp_authoritative=True,
        capture_phase="NCP_LOCKED",
        collection_started_at=datetime(
            2026, 6, 12, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta")
        ),
        decision_at=datetime(
            2026, 6, 12, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta")
        ),
        decision_snapshot_ref="test:ncp",
    )


def test_resolve_pre_open_result_status_matrix():
    assert (
        resolve_pre_open_result_status(
            source_status=PreOpenSourceStatus.LIVE_SUCCESS, candidate_count=1
        )
        is ScreenResultStatus.OK
    )
    assert (
        resolve_pre_open_result_status(
            source_status=PreOpenSourceStatus.LIVE_SUCCESS, candidate_count=0
        )
        is ScreenResultStatus.EMPTY
    )
    assert (
        resolve_pre_open_result_status(
            source_status=PreOpenSourceStatus.EMPTY_CONFIRMED, candidate_count=0
        )
        is ScreenResultStatus.EMPTY
    )
    assert (
        resolve_pre_open_result_status(
            source_status=PreOpenSourceStatus.UNAVAILABLE, candidate_count=0
        )
        is ScreenResultStatus.MISSING
    )
    assert (
        resolve_pre_open_result_status(
            source_status=PreOpenSourceStatus.OUTSIDE_WINDOW, candidate_count=0
        )
        is ScreenResultStatus.MISSING
    )


def test_build_pre_open_envelope_ok():
    envelope = build_pre_open_envelope(response=_response(candidates=[_candidate()]))
    assert envelope["verb"] == "pre-open"
    assert envelope["status"] == "ok"
    assert envelope["subject"] == {"kind": "screen", "id": "PRE-OPEN"}
    assert envelope["scope"] == "live"
    assert envelope["fetch_hint"] == "saham fetch iev"
    data = envelope["data"]
    assert data["schema_version"] == 2
    assert data["artifact_type"] == "pre_open_screen"
    assert data["source_is_live"] is True
    assert data["ncp_authoritative"] is True
    assert data["capture_phase"] == "NCP_LOCKED"
    assert data["collection_started_at"] == "2026-06-12T08:56:00+07:00"
    assert data["decision_at"] == "2026-06-12T08:57:00+07:00"
    assert data["decision_snapshot_ref"] == "test:ncp"
    assert data["candidates"][0]["ticker"] == "BBCA"
    assert data["data_freshness"]["candle_end"] == "2026-06-11"
    assert any(a["command"] == "saham view BBCA" for a in data["related_actions"])


def test_build_pre_open_envelope_unavailable_missing():
    envelope = build_pre_open_envelope(
        response=_response(
            candidates=[],
            source_status=PreOpenSourceStatus.UNAVAILABLE,
            source_message="auth failure",
        )
    )
    assert envelope["status"] == "missing"
    assert envelope["scope"] == "unavailable"
    assert envelope["scope_note"] == "auth failure"
    assert envelope["fetch_hint"] == default_pre_open_fetch_hint(
        PreOpenSourceStatus.UNAVAILABLE
    )


def test_build_pre_open_failure_envelope():
    envelope = build_pre_open_failure_envelope(
        status=ScreenResultStatus.ERROR,
        scope="guard",
        scope_note="non-trading day",
        data={"error": "non-trading day"},
    )
    assert envelope["status"] == "error"
    assert envelope["scope"] == "guard"
    assert envelope["data"]["error"] == "non-trading day"
