"""Unit tests for pre-open v1 signal cascade (ADR-048 Phase 1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from src.application.services.pre_open_signal_cascade import (
    PreOpenSignalInputsBuilder,
    evaluate_pre_open_signal_cascade,
    score_auction_ncp,
)
from src.application.services.pre_open_signal_config import PreOpenSignalConfig
from src.application.services.pre_open_signal_evidence_builder import (
    build_pre_open_signal_evidence,
)
from src.domain.value_objects.pre_open_signal_evidence import (
    AuctionNcpEvidence,
    AuctionNcpProvenance,
    OpenViabilityEvidence,
    PreOpenSignalEvidenceBundle,
)
from src.domain.value_objects.signal_assessment import EntryQuality, SignalStrength


def _auction(
    *,
    iev: int = 200_000,
    gap: float | None = 1.0,
    bid_pressure: float | None = 0.65,
    spread: float | None = 0.3,
) -> AuctionNcpEvidence:
    return AuctionNcpEvidence(
        ticker="BBCA",
        iev=iev,
        gap_pct=None if gap is None else Decimal(str(gap)),
        bid_pressure=bid_pressure,
        spread_pct=None if spread is None else Decimal(str(spread)),
        prev_close=Decimal("10000"),
        provenance=AuctionNcpProvenance(
            ticker="BBCA",
            decision_at=None,
            capture_phase="NCP_LOCKED",
            trade_date=date(2026, 6, 18),
        ),
    )


def test_hard_guard_no_auction_returns_none():
    bundle = PreOpenSignalEvidenceBundle(auction_ncp=None, open_viability=None)
    assert (
        evaluate_pre_open_signal_cascade(bundle, snapshot_date=date(2026, 6, 18))
        is None
    )


def test_hard_guard_auction_below_min_returns_none():
    cfg = PreOpenSignalConfig(auction_min=90)
    # Force low score: huge gap, weak pressure, wide spread
    auction = _auction(gap=12.0, bid_pressure=0.2, spread=3.0, iev=100_000)
    assert score_auction_ncp(auction) < 90
    bundle = PreOpenSignalEvidenceBundle(auction_ncp=auction, open_viability=None)
    assert (
        evaluate_pre_open_signal_cascade(
            bundle, snapshot_date=date(2026, 6, 18), config=cfg
        )
        is None
    )


def test_viability_missing_caps_strength_moderate():
    auction = _auction()
    assert score_auction_ncp(auction) >= 70  # would be STRONG if viability present
    bundle = PreOpenSignalEvidenceBundle(auction_ncp=auction, open_viability=None)
    resp = evaluate_pre_open_signal_cascade(
        bundle, snapshot_date=date(2026, 6, 18)
    )
    assert resp is not None
    assert resp.assessment.strength is SignalStrength.MODERATE
    assert resp.signal_authority_coverage == 0.5


def test_gap_out_veto_forces_avoid():
    auction = _auction(gap=1.0, bid_pressure=0.7)
    viability = OpenViabilityEvidence(
        ticker="BBCA",
        gap_out=True,
        friction_fail=False,
        unusual_volume=False,
        rsi_extension=False,
        trend_signal="GAP_OUT",
        iev_intensity=None,
        atr=None,
        gap_pct=Decimal("8"),
    )
    bundle = PreOpenSignalEvidenceBundle(
        auction_ncp=auction, open_viability=viability
    )
    resp = evaluate_pre_open_signal_cascade(
        bundle, snapshot_date=date(2026, 6, 18)
    )
    assert resp is not None
    assert resp.assessment.entry_quality is EntryQuality.AVOID
    assert any("gap_out" in r for r in resp.assessment.rationale)


def test_viability_does_not_boost_score_above_auction():
    auction = _auction(gap=1.0)
    auction_only = score_auction_ncp(auction)
    viability = OpenViabilityEvidence(
        ticker="BBCA",
        gap_out=False,
        friction_fail=False,
        unusual_volume=False,
        rsi_extension=False,
        trend_signal="BULLISH",
        iev_intensity=1.0,
        atr=Decimal("100"),
        gap_pct=Decimal("1"),
    )
    resp = evaluate_pre_open_signal_cascade(
        PreOpenSignalEvidenceBundle(auction_ncp=auction, open_viability=viability),
        snapshot_date=date(2026, 6, 18),
    )
    assert resp is not None
    assert resp.score == auction_only


def test_builder_from_candidate_and_evaluate():
    candidate = SimpleNamespace(
        ticker="BBRI",
        iev=250_000,
        prev_close=Decimal("5000"),
        gap_pct=Decimal("1.2"),
        bid_offer_imbalance=0.62,
        spread_pct=Decimal("0.4"),
        trend_signal="BULLISH",
        unusual_volume=False,
        iev_intensity=2.0,
        atr=Decimal("50"),
        rsi=Decimal("55"),
    )
    builder = PreOpenSignalInputsBuilder()
    resp = builder.evaluate(candidate, trade_date=date(2026, 6, 18))
    assert resp is not None
    assert resp.ticker == "BBRI"
    assert 0 <= resp.score <= 100


def test_builder_without_prev_close_no_auction():
    candidate = SimpleNamespace(
        ticker="BBRI",
        iev=250_000,
        prev_close=None,
        gap_pct=None,
        bid_offer_imbalance=None,
        spread_pct=None,
        trend_signal=None,
        unusual_volume=False,
        iev_intensity=None,
        atr=None,
        rsi=None,
    )
    bundle = build_pre_open_signal_evidence(
        candidate, trade_date=date(2026, 6, 18)
    )
    assert bundle.auction_ncp is None
    assert (
        evaluate_pre_open_signal_cascade(
            bundle, snapshot_date=date(2026, 6, 18)
        )
        is None
    )


def test_confirmation_only_impossible_without_auction():
    """Viability alone never produces a production signal."""
    viability = OpenViabilityEvidence(
        ticker="BBCA",
        gap_out=False,
        friction_fail=False,
        unusual_volume=False,
        rsi_extension=False,
        trend_signal="BULLISH",
        iev_intensity=1.0,
        atr=None,
        gap_pct=Decimal("1"),
    )
    bundle = PreOpenSignalEvidenceBundle(
        auction_ncp=None, open_viability=viability
    )
    assert (
        evaluate_pre_open_signal_cascade(
            bundle, snapshot_date=date(2026, 6, 18)
        )
        is None
    )


def test_composite_rendering_requires_auction_and_uses_weights():
    cfg = PreOpenSignalConfig(rendering="composite", auction_weight=0.65, viability_weight=0.35)
    auction = _auction(gap=1.0)
    viability = OpenViabilityEvidence(
        ticker="BBCA",
        gap_out=False,
        friction_fail=False,
        unusual_volume=False,
        rsi_extension=False,
        trend_signal="BULLISH",
        iev_intensity=1.0,
        atr=None,
        gap_pct=Decimal("1"),
    )
    resp = evaluate_pre_open_signal_cascade(
        PreOpenSignalEvidenceBundle(auction_ncp=auction, open_viability=viability),
        snapshot_date=date(2026, 6, 18),
        config=cfg,
    )
    assert resp is not None
    assert 0 <= resp.score <= 100
    assert "composite=" in " ".join(resp.assessment.rationale)
