"""Canonical Daily response fixtures for TUI adapter tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from src.application.use_case.daily_accumulation_projection import (
    DailyAccumulationCandidate,
    DailyAccumulationSummary,
)
from src.application.use_case.daily_briefing_use_case import (
    BriefingDataFreshnessItem,
    DailyBriefingResponse,
    DataReadiness,
    OpeningBriefingCandidate,
)
from src.application.use_case.daily_setup_lens_impact_use_case import (
    DailySetupLensImpactCell,
    DailySetupLensImpactResult,
    DailySetupLensImpactRow,
)
from src.domain.value_objects.data_freshness_status import (
    DataFreshnessStatus,
    SourceAlignmentState,
    SourceFreshnessState,
)
from src.domain.value_objects.market_context import (
    ContextFactor,
    MarketContext,
    MarketRegime,
)


def ready_response() -> DailyBriefingResponse:
    as_of = date(2026, 7, 21)
    freshness = DataFreshnessStatus(
        candle_as_of=as_of,
        broker_as_of=as_of,
        expected_latest_eod=as_of,
        candle_state=SourceFreshnessState.READY,
        broker_state=SourceFreshnessState.READY,
        alignment_state=SourceAlignmentState.ALIGNED,
        sources_aligned=True,
        signal_evidence_coverage=1.0,
    )
    regime = MarketContext(
        regime=MarketRegime.RISK_ON,
        conviction=0.75,
        factors=(
            ContextFactor(
                name="idx_trend",
                enabled=True,
                value=1.0,
                score=0.8,
                weight=1.0,
                label="FAVORABLE",
                rationale="local trend",
            ),
        ),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=as_of,
        regime_confidence=0.7,
        regime_stability="STABLE",
        days_in_regime=3,
    )
    return DailyBriefingResponse(
        live_session_date=date(2026, 7, 22),
        latest_completed_eod_date=as_of,
        opening_snapshot_date=date(2026, 7, 22),
        is_historical=False,
        universe="lq45",
        universe_count=1,
        data_freshness=[BriefingDataFreshnessItem("BBCA", freshness)],
        stale_count=0,
        readiness_items=[DataReadiness("candles", as_of, 1, 1, "READY")],
        overall_authority="READY",
        regime=regime,
        opening_candidates=[OpeningBriefingCandidate("BBCA", "PRIME", 100, 9000, "UP", 77.0)],
        accumulation_summary=DailyAccumulationSummary(1, 1, 1, 1, 0, 0, 0),
        daily_accumulation_candidates=[
            DailyAccumulationCandidate("BBCA", 77.0, "ACCUMULATION", 81, 1.0, "OPEN", "ENTER")
        ],
        setup_lens_impact=DailySetupLensImpactResult(
            rows=(
                DailySetupLensImpactRow(
                    ticker="BBCA",
                    base_action="ENTER",
                    cells=(
                        DailySetupLensImpactCell(
                            "foreign-bounce", "ENTER", 81, "MATCH", True, None
                        ),
                    ),
                ),
            ),
            warnings=("setup warning",),
        ),
        warnings=["local warning"],
    )


def partial_response() -> DailyBriefingResponse:
    response = ready_response()
    return replace(
        response,
        overall_authority="PARTIAL",
        readiness_items=[
            DataReadiness("brokers", date(2026, 7, 21), 1, 2, "PARTIAL", "one missing")
        ],
    )


def not_ready_response() -> DailyBriefingResponse:
    response = ready_response()
    return replace(
        response,
        overall_authority="NOT_READY",
        readiness_items=[DataReadiness("candles", date(2026, 7, 21), 0, 1, "NOT_READY", "missing")],
    )


def empty_response() -> DailyBriefingResponse:
    return DailyBriefingResponse(
        live_session_date=date(2026, 7, 22),
        latest_completed_eod_date=None,
        opening_snapshot_date=None,
        is_historical=False,
        universe="empty",
        universe_count=0,
        data_freshness=[],
        stale_count=0,
        readiness_items=[],
        overall_authority="NOT_READY",
    )
