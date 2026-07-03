"""
Phase 6 confidence-aware SignalEngine classification tests.

High score is no longer sufficient for ENTER. The evidence coverage/confidence
must also clear configured thresholds.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceRequest,
    AssessSignalEvidenceUseCase,
)
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import EntryQuality, SignalStrength


SNAP = date(2026, 7, 3)


def _setup(match: str) -> SetupEvidence:
    strength = {"MATCH": 100.0, "PARTIAL": 60.0, "NO_MATCH": 20.0}[match]
    return SetupEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        setup_name="foreign-bounce",
        setup_match=match,
        match_strength=strength,
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


def _flow(capped_strength: float) -> FlowConfirmationEvidence:
    signal = FlowSubSignal(
        key="flow",
        score=40.0,
        weight=40.0,
        direction=Direction.BULLISH,
        freshness=Freshness.FRESH,
    )
    return FlowConfirmationEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        flow_signals=(signal,),
        flow_score_ex_bb=40.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=capped_strength,
        capped_strength=capped_strength,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )


def _execute(**kwargs):
    req = AssessSignalEvidenceRequest(ticker="TEST", snapshot_date=SNAP, **kwargs)
    return AssessSignalEvidenceUseCase().execute(req)


def test_full_evidence_strong_score_can_enter():
    resp = _execute(
        setup_evidence=_setup("MATCH"),
        flow_confirmation_evidence=_flow(0.90),
    )

    assert resp.assessment.score == 96
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.confidence_score == pytest.approx(1.0)
    assert resp.assessment.entry_quality == EntryQuality.ENTER


def test_high_score_with_setup_only_confidence_becomes_watch_not_enter():
    resp = _execute(setup_evidence=_setup("MATCH"))

    assert resp.assessment.score == 100
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.confidence_score == pytest.approx(0.60)
    assert resp.assessment.entry_quality == EntryQuality.WATCH


def test_high_score_with_flow_only_confidence_becomes_watch_not_enter():
    resp = _execute(flow_confirmation_evidence=_flow(0.90))

    assert resp.assessment.score == 90
    assert resp.assessment.strength == SignalStrength.STRONG
    assert resp.assessment.confidence_score == pytest.approx(0.40)
    assert resp.assessment.entry_quality == EntryQuality.WATCH


def test_no_evidence_is_avoid_even_with_neutral_moderate_score():
    resp = _execute()

    assert resp.assessment.score == 50
    assert resp.assessment.strength == SignalStrength.MODERATE
    assert resp.assessment.confidence_score == pytest.approx(0.0)
    assert resp.assessment.entry_quality == EntryQuality.AVOID
