"""
Application-owned JSON payloads for `saham screen pre-open`.

Adapters dump the envelope; source-status → envelope-status mapping stays here.

Layer: Application
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping, Sequence

from src.application.dto.screen_contract import (
    ScreenResultStatus,
    ScreenSubjectKind,
    build_screen_envelope,
    related_actions_for_accum,
)
from src.application.use_case.pre_open_workflow_use_case import (
    PreOpenDataFreshness,
    PreOpenWorkflowResponse,
)
from src.domain.value_objects.pre_open_source_status import PreOpenSourceStatus
from src.domain.value_objects.screener_result import ScreenerCandidate


def resolve_pre_open_result_status(
    *,
    source_status: PreOpenSourceStatus,
    candidate_count: int,
) -> ScreenResultStatus:
    """Map pre-open source outcomes onto the shared envelope status vocabulary."""
    if source_status is PreOpenSourceStatus.UNAVAILABLE:
        return ScreenResultStatus.MISSING
    if source_status is PreOpenSourceStatus.OUTSIDE_WINDOW and candidate_count <= 0:
        return ScreenResultStatus.MISSING
    if (
        source_status is PreOpenSourceStatus.EMPTY_CONFIRMED
        or candidate_count <= 0
    ):
        return ScreenResultStatus.EMPTY
    return ScreenResultStatus.OK


def default_pre_open_fetch_hint(
    source_status: PreOpenSourceStatus | None = None,
) -> str:
    if source_status is PreOpenSourceStatus.UNAVAILABLE:
        return "saham fetch stockbit login"
    return "saham fetch iev"


def pre_open_scope(source_status: PreOpenSourceStatus) -> str:
    return {
        PreOpenSourceStatus.LIVE_SUCCESS: "live",
        PreOpenSourceStatus.SNAPSHOT_SUCCESS: "snapshot",
        PreOpenSourceStatus.EMPTY_CONFIRMED: "empty_confirmed",
        PreOpenSourceStatus.UNAVAILABLE: "unavailable",
        PreOpenSourceStatus.OUTSIDE_WINDOW: "outside_window",
    }.get(source_status, source_status.value.lower())


def _candidate_payload(candidate: ScreenerCandidate) -> dict[str, Any]:
    raw = asdict(candidate) if is_dataclass(candidate) else dict(candidate)
    return raw


def _freshness_payload(
    freshness: PreOpenDataFreshness | None,
) -> dict[str, Any] | None:
    if freshness is None:
        return None
    return {
        "analysis_date": freshness.analysis_date.isoformat(),
        "candle_end": (
            freshness.candle_end.isoformat() if freshness.candle_end else None
        ),
        "broker_end": (
            freshness.broker_end.isoformat() if freshness.broker_end else None
        ),
        "warnings": list(freshness.warnings),
    }


def build_pre_open_data(
    *,
    response: PreOpenWorkflowResponse,
) -> dict[str, Any]:
    result = response.result
    candidates = list(result.candidates)
    data: dict[str, Any] = {
        "schema_version": 1,
        "artifact_type": "pre_open_screen",
        "screened_date": result.screened_date.isoformat(),
        "iev_min": result.iev_min,
        "total_movers_seen": result.total_movers_seen,
        "candidate_count": len(candidates),
        "candidates": [_candidate_payload(c) for c in candidates],
        "warnings": list(response.warnings),
        "source_status": response.source_status.value,
        "source_message": response.source_message,
        "source_snapshot_ref": response.source_snapshot_ref,
        "data_freshness": _freshness_payload(response.data_freshness),
        "regime_enabled": response.regime_enabled,
        "risk_enabled": response.risk_enabled,
        "signal_enabled": response.signal_enabled,
        "related_actions": related_actions_for_accum(
            tickers=[c.ticker for c in candidates],
        ),
    }
    if response.risk_enabled:
        risk_payload: dict[str, Any] = {}
        for ticker, summary in (response.risk_by_ticker or {}).items():
            risk_payload[ticker] = summary.to_dict() if summary is not None else None
        data["risk_by_ticker"] = risk_payload
    if response.signal_enabled and response.signal_by_ticker is not None:
        sig_payload: dict[str, Any] = {}
        for ticker, summary in response.signal_by_ticker.items():
            sig_payload[ticker] = summary.to_dict() if summary is not None else None
        data["signal_by_ticker"] = sig_payload
    if response.trade_setup_by_ticker is not None:
        ts_payload: dict[str, Any] = {}
        for ticker, setup in response.trade_setup_by_ticker.items():
            if setup is None:
                ts_payload[ticker] = None
            elif hasattr(setup, "to_dict"):
                ts_payload[ticker] = setup.to_dict()
            else:
                ts_payload[ticker] = {
                    "action": setup.action.value,
                    "signal_score": setup.signal_score,
                    "signal_strength": setup.signal_strength.value
                    if hasattr(setup.signal_strength, "value")
                    else str(setup.signal_strength),
                }
        data["trade_setup_by_ticker"] = ts_payload
    if response.market_regime is not None and hasattr(response.market_regime, "to_dict"):
        data["market_regime"] = response.market_regime.to_dict()
    elif response.regime_enabled:
        data["market_regime"] = None
    return data


def build_pre_open_envelope(
    *,
    response: PreOpenWorkflowResponse,
) -> dict[str, Any]:
    """Full ADR-046 envelope for ``screen pre-open`` machine output."""
    result = response.result
    candidate_count = len(result.candidates)
    status = resolve_pre_open_result_status(
        source_status=response.source_status,
        candidate_count=candidate_count,
    )
    data = build_pre_open_data(response=response)
    scope_note = response.source_message
    if response.source_snapshot_ref and not scope_note:
        scope_note = f"Snapshot: {response.source_snapshot_ref}"
    return build_screen_envelope(
        verb="pre-open",
        status=status,
        subject_kind=ScreenSubjectKind.SCREEN,
        subject_id="PRE-OPEN",
        as_of=result.screened_date,
        source="pre_open_screen",
        scope=pre_open_scope(response.source_status),
        scope_note=scope_note,
        fetch_hint=default_pre_open_fetch_hint(response.source_status),
        data=data,
    )


def build_pre_open_failure_envelope(
    *,
    status: ScreenResultStatus,
    scope: str,
    scope_note: str | None,
    data: Mapping[str, Any] | None = None,
    fetch_hint: str | None = None,
) -> dict[str, Any]:
    """Envelope for pre-run guard/session failures (no workflow response)."""
    return build_screen_envelope(
        verb="pre-open",
        status=status,
        subject_kind=ScreenSubjectKind.SCREEN,
        subject_id="PRE-OPEN",
        source="pre_open_screen",
        scope=scope,
        scope_note=scope_note,
        fetch_hint=fetch_hint,
        data=dict(data or {}),
    )
