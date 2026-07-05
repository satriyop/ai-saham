from __future__ import annotations

from datetime import date

from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceRequest,
    AssessSignalEvidenceUseCase,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import EntryQuality


SNAP = date(2026, 7, 5)


def _mctx(regime: str) -> MarketContext:
    return MarketContext(
        regime=MarketRegime(regime),
        conviction=0.70,
        factors=(),
        signal_multiplier=1.0,
        gate_tightening=False,
        as_of_date=SNAP,
    )


def _setup() -> SetupEvidence:
    return SetupEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match="MATCH",
        match_strength=100.0,
        failed_gates=(),
        trend="UP",
        rsi=45.0,
        bb_width_pctile=0.20,
        vwap_discount_pct=1.5,
        vwap_pct=1.02,
        rs_vs_ihsg_5d=1.05,
        rs_freshness=Freshness.FRESH,
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
    )


def _flow() -> FlowConfirmationEvidence:
    sig = FlowSubSignal(
        key="cons",
        score=80.0,
        weight=40.0,
        direction=Direction.BULLISH,
        freshness=Freshness.FRESH,
    )
    return FlowConfirmationEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        flow_signals=(sig,),
        flow_score_ex_bb=80.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=0.80,
        capped_strength=0.80,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )


def test_risk_off_enter_allowed_false_caps_enter_without_mutating_score():
    response = AssessSignalEvidenceUseCase().execute(
        AssessSignalEvidenceRequest(
            ticker="TEST",
            snapshot_date=SNAP,
            setup_evidence=_setup(),
            flow_confirmation_evidence=_flow(),
            market_context=_mctx("RISK_OFF"),
            setup_family="foreign-bounce",
        )
    )

    assert response.assessment.score == 92
    assert response.assessment.entry_quality == EntryQuality.WATCH

    constraints = response.assessment.decision_constraints
    assert constraints is not None
    assert constraints.max_decision == "WATCH"
    assert constraints.regime == "RISK_OFF"
    assert constraints.regime_enter_allowed is False
    assert constraints.regime_size_multiplier == 0.25
    assert constraints.setup_family == "foreign_bounce"
    assert constraints.effective_size_multiplier == 0.25
    assert "RISK_OFF disables ENTER" in constraints.constraint_reasons
