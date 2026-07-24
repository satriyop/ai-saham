from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from src.application.dto.swing_analysis import (
    SignalAssessmentAvailability,
    SignalAssessmentStatus,
    SignalAssessmentUnavailableReason,
)
from src.application.services.screen_accum_result_projector import (
    MultiScreenAppliedFilters,
    ScreenAccumMultiProjection,
    ScreenAccumMultiRow,
    ScreenAccumSingleProjection,
    SingleScreenAppliedFilters,
)
from src.application.use_case.run_accumulation_screen_workflow_use_case import (
    RunAccumulationScreenWorkflowResult,
)


def _candidate(ticker: str, action: str):
    signal = SimpleNamespace(
        assessment=SimpleNamespace(score=71, signal_authority_coverage=0.82),
        coverage_warning=None,
    )
    return SimpleNamespace(
        ticker=ticker,
        accum_score=70.0,
        consecutive_streak=3,
        net_buy_ratio=0.5,
        bci_label=None,
        vwap_discount_pct=2.0,
        signal_assessment=signal,
        risk_assessment=SimpleNamespace(risk_level_name="OPEN"),
        setup_phase=SimpleNamespace(current_phase=SimpleNamespace(value="ACCUMULATION")),
        freshness=SimpleNamespace(alignment_state=SimpleNamespace(value="ALIGNED")),
        trade_setup=SimpleNamespace(action=SimpleNamespace(value=action)),
    )


def single_result() -> RunAccumulationScreenWorkflowResult:
    candidates = [_candidate("BBRI", "WATCH"), _candidate("BBCA", "ENTER")]
    projection = ScreenAccumSingleProjection(
        candidates=candidates,
        applied_filters=SingleScreenAppliedFilters(False, False, 0, 20, "vwap"),
        raw_candidate_count=2,
        projected_candidate_count=2,
        window_days=7,
        screened_at=date(2026, 7, 22),
        data_as_of={
            "latest_candle_date": "2026-07-21",
            "latest_broker_date": "2026-07-21",
        },
    )
    return RunAccumulationScreenWorkflowResult(
        single_projection=projection,
        warnings=("projection warning",),
    )


def multi_result() -> RunAccumulationScreenWorkflowResult:
    candidate = _candidate("TLKM", "WATCH")
    row = ScreenAccumMultiRow(
        ticker="TLKM",
        candidates_by_window={7: candidate, 30: None, 90: None},
        pattern="BUILDING",
        trend="UP",
        tracked_broker_flow=None,
        canonical_window=7,
        canonical_candidate=candidate,
        signal_score=71,
        signal_authority_coverage=0.82,
        risk_status="OPEN",
        setup_phase="ACCUMULATION",
        data_status="ALIGNED",
        next_action="WATCH",
    )
    projection = ScreenAccumMultiProjection(
        rows=[row],
        applied_filters=MultiScreenAppliedFilters(False, 20, "vwap"),
        requested_windows=[7, 30, 90],
        resolved_windows=[7, 30, 90],
        raw_ticker_count=1,
        projected_row_count=1,
        screened_at=date(2026, 7, 22),
        canonical_window=7,
        warnings=("multi warning",),
    )
    return RunAccumulationScreenWorkflowResult(multi_projection=projection)


class _TypedSection:
    def __init__(self, values):
        self.values = values

    def to_dict(self):
        return self.values


def ticker_response(
    *,
    ticker: str = "BBRI",
    available: bool = True,
    preview_action: str | None = "PREVIEW_ONLY",
):
    if available:
        availability = SignalAssessmentAvailability(SignalAssessmentStatus.AVAILABLE)
        signal = SimpleNamespace(
            assessment=SimpleNamespace(score=73, signal_authority_coverage=0.8)
        )
        trade_setup = SimpleNamespace(action=SimpleNamespace(value="CANONICAL_ONLY"))
    else:
        availability = SignalAssessmentAvailability(
            SignalAssessmentStatus.UNAVAILABLE,
            SignalAssessmentUnavailableReason.NO_PRODUCTION_SIGNAL_EVIDENCE,
        )
        signal = None
        trade_setup = None
    preview = (
        SimpleNamespace(action=SimpleNamespace(value=preview_action))
        if preview_action is not None
        else None
    )
    verdict = SimpleNamespace(
        signal_assessment_availability=availability,
        signal_assessment=signal,
        trade_setup=trade_setup,
        risk_response=SimpleNamespace(assessment=SimpleNamespace(risk_level_name="OPEN")),
        market_regime=None,
        market_context_signal_preview=None,
        market_context_risk_preview=None,
        market_context_trade_setup_preview=preview,
    )
    return SimpleNamespace(
        ticker=ticker,
        verdict=verdict,
        evidence=_TypedSection({"flow": {"status": "AVAILABLE"}}),
        diagnostics=_TypedSection({"data": {"state": "CURRENT"}}),
        warnings=("ticker warning",),
    )
