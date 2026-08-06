"""
Phase 5 — regime-conditional signal interpretation tests.

Covers:
  - RISK_ON: no conditioning fires
  - NEUTRAL: weak flow (< 50) discounted, strong flow unchanged
  - RISK_OFF: weak setup (< 60) discounted, strong setup (>= 60) unchanged
  - VOLATILE: both groups discounted unconditionally
  - No evidence: conditioning is no-op (nothing to discount)
  - gate_tightening=True: ENTER capped to WATCH
  - gate_tightening=False: ENTER preserved
  - Regime notes appear in rationale when conditioning fires
  - No notes when conditioning does not fire (RISK_ON, strong evidence)
  - regime_conditioning=1.0 in breakdown when conditioning fires
  - gate_tightening=1.0 in breakdown when gate fires
  - Regime applied exactly once per execute() call (no double-apply)
"""

from __future__ import annotations

from datetime import date

import pytest

from src.application.dto.assess_signal import AssessSignalEvidenceRequest
from src.application.use_case.assess_signal_evidence_use_case import (
    AssessSignalEvidenceUseCase,
)
from src.domain.value_objects.benchmark_excess_return import (
    BenchmarkExcessReturn,
    BenchmarkExcessReturnStatus,
)
from src.domain.value_objects.canonical_signal_evidence_input import CanonicalSignalEvidenceInput
from src.domain.value_objects.factor_evidence import Direction, Freshness
from src.domain.value_objects.flow_confirmation_evidence import (
    FlowConfirmationEvidence,
    FlowSubSignal,
)
from src.domain.value_objects.market_context import MarketContext, MarketRegime
from src.domain.value_objects.setup_evidence import SetupEvidence
from src.domain.value_objects.signal_assessment import (
    SWING_TRADE_SETUP_IDENTITY,
    EntryQuality,
)
from tests.application.use_case.signal_evidence_fixtures import (
    _wrap_flow_evidence,
    _wrap_setup_evidence,
)

SNAP = date(2026, 7, 3)


def _excess_return(window_sessions: int, excess_return_pct: float) -> BenchmarkExcessReturn:
    return BenchmarkExcessReturn(
        benchmark="IHSG",
        window_sessions=window_sessions,
        ticker_return_pct=excess_return_pct,
        benchmark_return_pct=0.0,
        excess_return_pct=excess_return_pct,
        window_start=date(2026, 6, 1),
        window_end=SNAP,
        common_session_count=window_sessions + 1,
        status=BenchmarkExcessReturnStatus.AVAILABLE,
        unavailable_reason=None,
    )


UC = AssessSignalEvidenceUseCase()


# ── fixtures ──────────────────────────────────────────────────────────────────

_SETUP_STRENGTHS = {"MATCH": 100.0, "PARTIAL": 60.0, "NO_MATCH": 20.0}


def _setup(match: str = "MATCH") -> SetupEvidence:
    """SetupEvidence with match_strength constrained to {100.0, 60.0, 20.0}."""
    strength = _SETUP_STRENGTHS[match]
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
        benchmark_excess_return_5_session=_excess_return(5, 1.05),
        benchmark_excess_return_20_session=_excess_return(20, 1.05),
        volume_trend_ratio=1.2,
        volume_freshness=Freshness.FRESH,
        candle_source="stockbit",
    )


def _flow(capped: float = 0.70) -> FlowConfirmationEvidence:
    sig = FlowSubSignal(
        key="cons",
        score=40.0,
        weight=40.0,
        direction=Direction.BULLISH,
        freshness=Freshness.FRESH,
    )
    return FlowConfirmationEvidence(
        ticker="TEST",
        snapshot_date=SNAP,
        flow_signals=(sig,),
        flow_score_ex_bb=40.0,
        confirmation_status="CONFIRMED",
        flow_direction="POSITIVE",
        bandar_broad_score=None,
        bandar_direction=Direction.NEUTRAL,
        bandar_freshness=Freshness.MISSING,
        bci_label=None,
        bci_tier1_count=0,
        uncapped_strength=capped,
        capped_strength=capped,
        group_cap=0.80,
        group_freshness=Freshness.FRESH,
    )


def _mctx(
    regime: str,
    multiplier: float = 1.0,
    gate_tightening: bool = False,
) -> MarketContext:
    return MarketContext(
        regime=MarketRegime(regime),
        conviction=0.7,
        factors=(),
        signal_multiplier=multiplier,
        gate_tightening=gate_tightening,
        as_of_date=SNAP,
    )


def _req(**kwargs) -> AssessSignalEvidenceRequest:
    setup_evidence = kwargs.pop("setup_evidence", None)
    flow_confirmation_evidence = kwargs.pop("flow_confirmation_evidence", None)
    if "canonical_evidence" not in kwargs and (
        setup_evidence is not None or flow_confirmation_evidence is not None
    ):
        kwargs["canonical_evidence"] = CanonicalSignalEvidenceInput(
            setup=_wrap_setup_evidence(setup_evidence),
            flow=_wrap_flow_evidence(flow_confirmation_evidence),
        )
    defaults = {
        "identity": SWING_TRADE_SETUP_IDENTITY,
        "ticker": "TEST",
        "snapshot_date": SNAP,
    }
    defaults.update(kwargs)
    return AssessSignalEvidenceRequest(**defaults)


def _breakdown_dict(r) -> dict:
    return dict(r.assessment.breakdown)


# ── RISK_ON — no conditioning ─────────────────────────────────────────────────


def test_risk_on_no_conditioning_fires():
    """RISK_ON should never modify group scores regardless of strength."""
    ctx = _mctx("RISK_ON")
    # Weak NO_MATCH setup (score=20), weak flow (capped=0.30) — but RISK_ON, no conditioning
    r = UC.execute(
        _req(
            setup_evidence=_setup("NO_MATCH"),
            flow_confirmation_evidence=_flow(0.30),
            market_context=ctx,
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(20.0)
    assert bd.get("flow_confirmation_group") == pytest.approx(30.0)
    assert "regime_conditioning" not in bd
    assert not any("RISK_ON" in line for line in r.assessment.rationale)


# ── NEUTRAL — weak flow discounted ────────────────────────────────────────────


def test_neutral_weak_flow_is_discounted():
    """NEUTRAL + flow_group_score < 50 → flow multiplied by 0.80."""
    r = UC.execute(
        _req(
            flow_confirmation_evidence=_flow(0.40),  # score = 40.0 < 50
            market_context=_mctx("NEUTRAL"),
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("flow_confirmation_group") == pytest.approx(40.0)
    assert r.assessment.legacy_conditioned_score == 32
    assert r.assessment.score == 40
    assert bd.get("regime_conditioning") == 1.0
    assert any("NEUTRAL" in line for line in r.assessment.rationale)


def test_neutral_strong_flow_unchanged():
    """NEUTRAL + flow_group_score >= 50 → no conditioning fires."""
    r = UC.execute(
        _req(
            flow_confirmation_evidence=_flow(0.60),  # score = 60.0 >= 50
            market_context=_mctx("NEUTRAL"),
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("flow_confirmation_group") == pytest.approx(60.0)
    assert "regime_conditioning" not in bd


def test_neutral_only_discounts_flow_not_setup():
    """NEUTRAL conditioning targets flow only; setup group is unaffected.

    ADR-067: with setup retired from the evidence basis, the conditioned setup
    score no longer reaches legacy_conditioned_score either, so attaching setup
    evidence produces byte-identical diagnostic output to flow alone.
    """
    r = UC.execute(
        _req(
            setup_evidence=_setup("NO_MATCH"),  # weak setup (score=20) — unchanged by NEUTRAL
            flow_confirmation_evidence=_flow(0.40),  # weak flow (score=40) → discounted
            market_context=_mctx("NEUTRAL"),
        )
    )
    flow_only = UC.execute(
        _req(
            flow_confirmation_evidence=_flow(0.40),
            market_context=_mctx("NEUTRAL"),
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(20.0)  # reported, not scored
    assert bd.get("flow_confirmation_group") == pytest.approx(40.0)  # unchanged (neutral)
    assert r.assessment.legacy_conditioned_score == 32  # 40 × 0.80, flow alone
    assert r.assessment.legacy_conditioned_score == flow_only.assessment.legacy_conditioned_score
    assert r.assessment.score == flow_only.assessment.score


# ── RISK_OFF — weak setup discounted ─────────────────────────────────────────


def test_risk_off_weak_setup_discount_cannot_move_any_score():
    """RISK_OFF still discounts weak setup, and it no longer changes anything.

    The branch fires (regime_conditioning flag set, RISK_OFF note emitted), but
    ADR-067 removed setup from the evidence basis, so the discounted value
    reaches neither the canonical score nor legacy_conditioned_score. Proven by
    comparing a discounted NO_MATCH against an undiscounted MATCH: identical
    scores, different notes.
    """
    weak = UC.execute(
        _req(setup_evidence=_setup("NO_MATCH"), market_context=_mctx("RISK_OFF"))
    )  # score=20.0 < 60 → discounted
    strong = UC.execute(
        _req(setup_evidence=_setup("MATCH"), market_context=_mctx("RISK_OFF"))
    )  # score=100.0 >= 60 → not discounted

    bd = _breakdown_dict(weak)
    assert bd.get("setup_quality_group") == pytest.approx(20.0)
    assert bd.get("regime_conditioning") == 1.0
    assert any("RISK_OFF" in line for line in weak.assessment.rationale)

    # No flow evidence, so both are the 50.0 neutral prior — not the setup score.
    assert weak.assessment.score == 50
    assert weak.assessment.legacy_conditioned_score == 50
    assert weak.assessment.score == strong.assessment.score
    assert weak.assessment.legacy_conditioned_score == strong.assessment.legacy_conditioned_score


def test_risk_off_strong_setup_unchanged():
    """RISK_OFF + setup_group_score >= 60 (MATCH quality) → no conditioning fires."""
    r = UC.execute(
        _req(
            setup_evidence=_setup("MATCH"),  # score = 100 >= 60
            market_context=_mctx("RISK_OFF"),
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(100.0)
    assert "regime_conditioning" not in bd


def test_risk_off_partial_setup_unchanged():
    """RISK_OFF + setup_group_score == 60 (PARTIAL boundary) → NOT discounted (< 60 required)."""
    r = UC.execute(
        _req(
            setup_evidence=_setup("PARTIAL"),  # score = 60.0 — boundary, NOT < 60
            market_context=_mctx("RISK_OFF"),
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(60.0)
    assert "regime_conditioning" not in bd


def test_risk_off_does_not_discount_flow():
    """RISK_OFF only targets setup; flow group unaffected."""
    r = UC.execute(
        _req(
            setup_evidence=_setup("NO_MATCH"),  # score=20 — discounted by RISK_OFF
            flow_confirmation_evidence=_flow(0.30),  # score=30 — NOT discounted by RISK_OFF
            market_context=_mctx("RISK_OFF"),
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(20.0)
    assert bd.get("flow_confirmation_group") == pytest.approx(30.0)
    # ADR-067: the diagnostic score is the (undiscounted) flow score alone.
    assert r.assessment.legacy_conditioned_score == 30


# ── VOLATILE — both groups discounted ────────────────────────────────────────


def test_volatile_discounts_both_groups():
    """VOLATILE conditions both groups; only flow reaches the diagnostic score.

    ADR-067: the setup discount is still computed and still noted, but with
    setup out of the evidence basis legacy_conditioned_score is 80 × 0.80 = 64,
    and the canonical score is the undiscounted flow score, 80.
    """
    r = UC.execute(
        _req(
            setup_evidence=_setup("MATCH"),  # score=100
            flow_confirmation_evidence=_flow(0.80),  # score=80
            market_context=_mctx("VOLATILE"),
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(100.0)
    assert bd.get("flow_confirmation_group") == pytest.approx(80.0)
    assert r.assessment.legacy_conditioned_score == 64
    assert r.assessment.score == 80
    assert bd.get("regime_conditioning") == 1.0
    assert any("VOLATILE" in line for line in r.assessment.rationale)


def test_volatile_with_only_setup():
    """VOLATILE with only setup evidence — no production evidence is present.

    ADR-067: setup alone leaves the evidence basis empty, so both the canonical
    and the diagnostic score are the 50.0 neutral prior no matter how strong
    the setup is or what discount VOLATILE applies to it.
    """
    r = UC.execute(
        _req(
            setup_evidence=_setup("MATCH"),  # score=100
            market_context=_mctx("VOLATILE"),
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(100.0)
    assert r.assessment.legacy_conditioned_score == 50
    assert r.assessment.score == 50


def test_volatile_with_only_flow():
    """VOLATILE with only flow evidence — only flow discounted, setup absent."""
    r = UC.execute(
        _req(
            flow_confirmation_evidence=_flow(0.60),  # score = 60
            market_context=_mctx("VOLATILE"),
        )
    )
    bd = _breakdown_dict(r)
    assert "setup_quality_group" not in bd
    assert bd.get("flow_confirmation_group") == pytest.approx(60.0)
    assert r.assessment.legacy_conditioned_score == 48
    assert r.assessment.score == 60


# ── no evidence — no conditioning ────────────────────────────────────────────


def test_no_evidence_conditioning_is_noop():
    from src.application.exceptions import NoProductionSignalEvidenceError

    for regime in ("NEUTRAL", "RISK_OFF", "VOLATILE"):
        with pytest.raises(NoProductionSignalEvidenceError):
            UC.execute(_req(market_context=_mctx(regime)))


def test_no_market_context_baseline():
    """Without market_context, scores are unmodified (regression guard)."""
    r = UC.execute(
        _req(
            setup_evidence=_setup("NO_MATCH"),  # score=20
            flow_confirmation_evidence=_flow(0.40),  # score=40
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(20.0)
    assert bd.get("flow_confirmation_group") == pytest.approx(40.0)
    assert "regime_conditioning" not in bd


# ── gate tightening ───────────────────────────────────────────────────────────


def test_gate_tightening_caps_enter_to_watch():
    """gate_tightening=True turns ENTER → WATCH after classification."""
    # Score high enough to be STRONG/ENTER without gate
    r_no_gate = UC.execute(
        _req(
            setup_evidence=_setup("MATCH"),
            flow_confirmation_evidence=_flow(0.90),
            market_context=_mctx("RISK_ON", gate_tightening=False),
        )
    )
    assert r_no_gate.assessment.entry_quality == EntryQuality.ENTER

    r_gate = UC.execute(
        _req(
            setup_evidence=_setup("MATCH"),
            flow_confirmation_evidence=_flow(0.90),
            market_context=_mctx("RISK_ON", gate_tightening=True),
        )
    )
    assert r_gate.assessment.entry_quality == EntryQuality.WATCH
    assert dict(r_gate.assessment.breakdown).get("gate_tightening") == 1.0
    assert any("ENTER → WATCH" in line for line in r_gate.assessment.rationale)


def test_gate_tightening_does_not_affect_watch_or_avoid():
    """gate_tightening only caps ENTER; WATCH and AVOID are unchanged.

    Scores are placed with flow evidence: ADR-067 left flow the sole production
    evidence group, so setup evidence can no longer put a score in a band.
    """
    # flow 0.60 → score 60 is MODERATE (45 ≤ 60 < 70) → WATCH
    r_watch = UC.execute(
        _req(
            flow_confirmation_evidence=_flow(0.60),
            market_context=_mctx("RISK_ON", gate_tightening=True),
        )
    )
    assert r_watch.assessment.entry_quality == EntryQuality.WATCH
    assert "gate_tightening" not in dict(r_watch.assessment.breakdown)

    # flow 0.20 → score 20 is WEAK (< 45) → AVOID
    r_avoid = UC.execute(
        _req(
            flow_confirmation_evidence=_flow(0.20),
            market_context=_mctx("RISK_ON", gate_tightening=True),
        )
    )
    assert r_avoid.assessment.entry_quality == EntryQuality.AVOID


def test_gate_tightening_note_in_rationale():
    """Gate tightening note appears in rationale when fired."""
    r = UC.execute(
        _req(
            setup_evidence=_setup("MATCH"),
            flow_confirmation_evidence=_flow(0.90),
            market_context=_mctx("RISK_ON", gate_tightening=True),
        )
    )
    rationale_text = " ".join(r.assessment.rationale)
    assert "Gate tightening" in rationale_text


# ── conditioning applied exactly once ────────────────────────────────────────


def test_regime_conditioning_applied_exactly_once():
    """Each execute() applies conditioning once. Two calls are idempotent (separate responses)."""
    setup = _setup("MATCH")  # score=100 → after VOLATILE: 70
    flow = _flow(0.40)  # score=40 → after VOLATILE: 32
    ctx = _mctx("VOLATILE")

    r1 = UC.execute(
        _req(
            setup_evidence=setup,
            flow_confirmation_evidence=flow,
            market_context=ctx,
        )
    )
    r2 = UC.execute(
        _req(
            setup_evidence=setup,
            flow_confirmation_evidence=flow,
            market_context=ctx,
        )
    )

    # Both calls produce identical results — no accumulated discount
    assert r1.assessment.score == r2.assessment.score
    assert r1.assessment.legacy_conditioned_score == r2.assessment.legacy_conditioned_score
    bd1 = _breakdown_dict(r1)
    bd2 = _breakdown_dict(r2)
    assert bd1.get("setup_quality_group") == bd2.get("setup_quality_group")
    assert bd1.get("flow_confirmation_group") == bd2.get("flow_confirmation_group")


# ── combined: regime + flags ──────────────────────────────────────────────────


def test_regime_conditioning_and_flags_both_apply():
    """Regime conditioning + do-no-harm flag penalties are independent — both fire."""
    from src.domain.value_objects.signal_assessment import SignalContext

    ctx_sig = SignalContext(
        ticker="TEST",
        snapshot_date=SNAP,
        forward_pe=60.0,  # triggers VALUATION_STRETCHED (-10)
    )
    r = UC.execute(
        _req(
            setup_evidence=_setup("NO_MATCH"),  # score=20, reported but not scored
            market_context=_mctx("RISK_OFF"),
            signal_context=ctx_sig,
        )
    )
    bd = _breakdown_dict(r)
    assert bd.get("setup_quality_group") == pytest.approx(20.0)
    assert bd.get("flag_adjustment") == -10.0  # VALUATION_STRETCHED
    assert bd.get("regime_conditioning") == 1.0
    # ADR-067: no production evidence present → 50.0 neutral prior. The flag
    # still applies independently of regime conditioning, which is the point of
    # this test: 50 - 10 = 40 on both the canonical and the diagnostic score.
    assert r.assessment.legacy_conditioned_score == 40
    assert r.assessment.score == 40
