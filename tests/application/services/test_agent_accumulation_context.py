from datetime import date
from decimal import Decimal

import pytest

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.application.dto.assess_signal import AssessSignalResponse
from src.application.services.agent_accumulation_context import (
    AgentContextInvariantError,
    build_agent_accumulation_context,
)
from src.domain.value_objects.accum_score_breakdown import (
    AccumScoreBreakdown,
    ForeignFlowComponentScore,
    ForeignFlowComponentStatus,
)
from src.domain.value_objects.signal_assessment import (
    ACCUMULATION_DISCOVERY_IDENTITY,
    EntryQuality,
    SignalAssessment,
    SignalStrength,
)
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup

pytestmark = pytest.mark.agent


def make_candidate(*, trade_ticker: str = "BBCA") -> AccumulationCandidate:
    snapshot = date(2026, 8, 1)
    components = tuple(
        ForeignFlowComponentScore(key, 1.0, 10.0, ForeignFlowComponentStatus.AVAILABLE)
        for key in ("cons", "streak", "vwap", "rsi", "flow", "bb", "inst")
    )
    breakdown = AccumScoreBreakdown(
        ticker="BBCA",
        snapshot_date=snapshot,
        components=components,
        vwap_discount_pct=-1.1,
        rsi=52.0,
        avg_flow_ratio=0.2,
        bb_width_pctile=0.3,
        bci_label="STABLE",
    )
    signal = SignalAssessment(
        identity=ACCUMULATION_DISCOVERY_IDENTITY,
        ticker="BBCA",
        score=72,
        strength=SignalStrength.MODERATE,
        entry_quality=EntryQuality.WATCH,
        breakdown=(("flow", 72.0),),
        rationale=("Canonical flow evidence",),
        snapshot_date=snapshot,
        signal_authority_coverage=1.0,
    )
    response = AssessSignalResponse(ticker="BBCA", assessment=signal)
    trade = TradeSetup(
        ticker=trade_ticker,
        snapshot_date=snapshot,
        action=SetupAction.WATCH,
        signal_score=72,
        signal_score_raw=72,
        signal_strength=SignalStrength.MODERATE,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="Wait for confirmation",
    )
    return AccumulationCandidate(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.7,
        total_net_value=Decimal("1000000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("9000"),
        current_price=Decimal("9100"),
        vwap_discount_pct=-1.1,
        rsi=52.0,
        trend="UP",
        accum_score=breakdown.accum_score,
        top_brokers=["AK"],
        institutional_flag=True,
        accum_score_breakdown=breakdown,
        signal_assessment=response,
        trade_setup=trade,
        latest_candle_date=snapshot,
        latest_broker_date=snapshot,
    )


def test_projection_is_allow_listed_and_digest_is_stable() -> None:
    candidate = make_candidate()
    first = build_agent_accumulation_context(candidate)
    second = build_agent_accumulation_context(candidate)

    assert first.schema_id == "tui_agent.accum_judge.v1"
    assert first.context_reference == second.context_reference
    assert first.context_reference.startswith("sha256:")
    payload = first.canonical_payload()
    assert "context_reference" not in payload
    assert payload["trade_setup"]["action"] == "WATCH"
    assert payload["top_brokers"] == ["AK"]
    assert payload["institutional_flag"] is True
    assert "named_setup_evaluations" not in payload


def test_projection_fails_closed_on_identity_mismatch() -> None:
    with pytest.raises(AgentContextInvariantError, match="ticker mismatch"):
        build_agent_accumulation_context(make_candidate(trade_ticker="TLKM"))


def test_risk_snapshot_lag_is_warning_not_hard_fail() -> None:
    """Live boards often have Risk as-of behind Signal/Trade/Accum — still explainable."""
    from dataclasses import replace
    from datetime import timedelta

    from src.domain.value_objects.risk_assessment import RiskAssessment

    candidate = make_candidate()
    lag = RiskAssessment(
        rationale=("open",),
        snapshot_date=candidate.trade_setup.snapshot_date - timedelta(days=3),
        indicators=None,  # type: ignore[arg-type]
        gate_triggered=None,
    )
    candidate = replace(candidate, risk_assessment=lag)

    context = build_agent_accumulation_context(candidate)
    assert context.risk is not None
    assert context.risk.snapshot_date == lag.snapshot_date
    assert context.as_of == candidate.trade_setup.snapshot_date
    assert any("Risk snapshot" in item and "differs" in item for item in context.warnings)
