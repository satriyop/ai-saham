"""Unit tests for pre-open v1 signal cascade (ADR-048 Phase 1)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

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
    PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT,
    AuctionNcpEvidence,
    AuctionNcpProvenance,
    OpenViabilityEvidence,
    PreOpenSignalEvidenceBundle,
)
from src.domain.value_objects.signal_assessment import EntryQuality, SignalStrength

NCP_DECISION_AT = datetime(2026, 6, 18, 8, 57, tzinfo=ZoneInfo("Asia/Jakarta"))
NCP_COLLECTION_STARTED_AT = datetime(2026, 6, 18, 8, 56, tzinfo=ZoneInfo("Asia/Jakarta"))
NCP_SNAPSHOT_REF = "test:ncp:2026-06-18T08:57:00+07:00"


def test_pre_open_signal_evidence_contract_is_v3():
    assert PRE_OPEN_SIGNAL_EVIDENCE_CONTRACT == "pre_open_signal_evidence.v3"


def _ncp_kwargs() -> dict:
    return {
        "collection_started_at": NCP_COLLECTION_STARTED_AT,
        "decision_at": NCP_DECISION_AT,
        "capture_phase": "NCP_LOCKED",
        "source_is_live": True,
        "snapshot_ref": NCP_SNAPSHOT_REF,
    }


def _auction(
    *,
    iev: int = 200_000,
    gap: float | None = 1.0,
    bid_pressure: float | None = 0.65,
    spread: float | None = 0.3,
    delta_iev: int | None = None,
) -> AuctionNcpEvidence:
    gap_pct = None if gap is None else Decimal(str(gap))
    return AuctionNcpEvidence(
        ticker="BBCA",
        iev=iev,
        gap_pct=gap_pct,
        bid_pressure=bid_pressure,
        spread_pct=None if spread is None else Decimal(str(spread)),
        prev_close=Decimal("10000"),
        provenance=AuctionNcpProvenance(
            ticker="BBCA",
            collection_started_at=NCP_COLLECTION_STARTED_AT,
            decision_at=NCP_DECISION_AT,
            capture_phase="NCP_LOCKED",
            source_is_live=True,
            snapshot_ref=NCP_SNAPSHOT_REF,
            trade_date=date(2026, 6, 18),
        ),
        iep=(None if gap_pct is None else int(Decimal("10000") * (Decimal("1") + gap_pct / 100))),
        iep_gap_pct=gap_pct,
        gap_price_source="IEP" if gap_pct is not None else None,
        delta_iev=delta_iev,
    )


def test_auction_evidence_rejects_unproven_ncp_provenance():
    with pytest.raises(ValueError, match="collection window wholly"):
        AuctionNcpEvidence(
            ticker="BBCA",
            iev=200_000,
            gap_pct=Decimal("1"),
            bid_pressure=0.6,
            spread_pct=Decimal("0.3"),
            prev_close=Decimal("10000"),
            provenance=AuctionNcpProvenance(
                ticker="BBCA",
                collection_started_at=NCP_COLLECTION_STARTED_AT,
                decision_at=None,
                capture_phase="NCP_LOCKED",
                source_is_live=True,
                snapshot_ref="claimed-ncp",
                trade_date=date(2026, 6, 18),
            ),
        )


def test_auction_evidence_rejects_iep_source_without_iep_fields():
    with pytest.raises(ValueError, match="requires iep and iep_gap_pct"):
        AuctionNcpEvidence(
            ticker="BBCA",
            iev=200_000,
            gap_pct=Decimal("1"),
            bid_pressure=0.6,
            spread_pct=Decimal("0.3"),
            prev_close=Decimal("10000"),
            provenance=AuctionNcpProvenance(
                ticker="BBCA",
                collection_started_at=NCP_COLLECTION_STARTED_AT,
                decision_at=NCP_DECISION_AT,
                capture_phase="NCP_LOCKED",
                source_is_live=True,
                snapshot_ref=NCP_SNAPSHOT_REF,
                trade_date=date(2026, 6, 18),
            ),
            gap_price_source="IEP",
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
            NCP_COLLECTION_STARTED_AT,
            None,
            "NCP_LOCKED",
            True,
            "test:missing-time",
        ),
        (
            NCP_COLLECTION_STARTED_AT,
            NCP_DECISION_AT,
            "UNKNOWN",
            True,
            "test:unknown-phase",
        ),
        (
            NCP_COLLECTION_STARTED_AT,
            NCP_DECISION_AT,
            "NCP_LOCKED",
            True,
            None,
        ),
        (
            datetime(2026, 6, 18, 8, 55, tzinfo=ZoneInfo("Asia/Jakarta")),
            NCP_DECISION_AT,
            "NCP_LOCKED",
            True,
            "test:started-before-ncp",
        ),
        (
            NCP_COLLECTION_STARTED_AT,
            datetime(2026, 6, 18, 8, 58, tzinfo=ZoneInfo("Asia/Jakarta")),
            "NCP_LOCKED",
            True,
            "test:matching-started",
        ),
        (
            NCP_COLLECTION_STARTED_AT,
            datetime(2026, 6, 18, 9, 0, tzinfo=ZoneInfo("Asia/Jakarta")),
            "NCP_LOCKED",
            True,
            "test:finished-after-ncp",
        ),
        (
            NCP_COLLECTION_STARTED_AT,
            NCP_DECISION_AT,
            "NCP_LOCKED",
            False,
            "test:manual-json",
        ),
    ],
)
def test_builder_keeps_unproven_auction_discovery_only(
    collection_started_at,
    decision_at,
    capture_phase,
    source_is_live,
    snapshot_ref,
):
    candidate = SimpleNamespace(
        ticker="BBRI",
        iev=500_000,
        prev_close=Decimal("5000"),
        gap_pct=Decimal("1.2"),
        iep=5060,
        iep_gap_pct=Decimal("1.2"),
        bid_gap_pct=Decimal("0.8"),
        gap_price_source="IEP",
        bid_offer_imbalance=0.7,
        spread_pct=Decimal("0.3"),
        trend_signal="BULLISH",
        unusual_volume=False,
        iev_intensity=2.0,
        atr=Decimal("50"),
        rsi=Decimal("55"),
    )

    bundle = build_pre_open_signal_evidence(
        candidate,
        trade_date=date(2026, 6, 18),
        collection_started_at=collection_started_at,
        decision_at=decision_at,
        capture_phase=capture_phase,
        source_is_live=source_is_live,
        snapshot_ref=snapshot_ref,
    )

    assert bundle.auction_ncp is None
    assert bundle.open_viability is not None


def test_hard_guard_no_auction_returns_none():
    bundle = PreOpenSignalEvidenceBundle(auction_ncp=None, open_viability=None)
    assert evaluate_pre_open_signal_cascade(bundle, snapshot_date=date(2026, 6, 18)) is None


def test_hard_guard_auction_below_min_returns_none():
    cfg = PreOpenSignalConfig(auction_min=90)
    # Force low score: huge gap, weak pressure, wide spread
    auction = _auction(gap=12.0, bid_pressure=0.2, spread=3.0, iev=100_000)
    assert score_auction_ncp(auction) < 90
    bundle = PreOpenSignalEvidenceBundle(auction_ncp=auction, open_viability=None)
    assert (
        evaluate_pre_open_signal_cascade(bundle, snapshot_date=date(2026, 6, 18), config=cfg)
        is None
    )


def test_viability_missing_caps_strength_moderate():
    auction = _auction()
    assert score_auction_ncp(auction) >= 70  # would be STRONG if viability present
    bundle = PreOpenSignalEvidenceBundle(auction_ncp=auction, open_viability=None)
    resp = evaluate_pre_open_signal_cascade(bundle, snapshot_date=date(2026, 6, 18))
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
    bundle = PreOpenSignalEvidenceBundle(auction_ncp=auction, open_viability=viability)
    resp = evaluate_pre_open_signal_cascade(bundle, snapshot_date=date(2026, 6, 18))
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


def test_delta_iev_missing_is_neutral_not_penalty():
    base = _auction(delta_iev=None)
    with_flat = _auction(delta_iev=0)
    assert score_auction_ncp(base) == score_auction_ncp(with_flat)


def test_delta_iev_build_boosts_fade_penalizes():
    # Mid-range base so ±contrib is visible (not already clamped at 100)
    missing = score_auction_ncp(
        _auction(iev=150_000, gap=3.0, bid_pressure=0.5, spread=0.8, delta_iev=None)
    )
    build = score_auction_ncp(
        _auction(iev=150_000, gap=3.0, bid_pressure=0.5, spread=0.8, delta_iev=40_000)
    )
    fade = score_auction_ncp(
        _auction(iev=150_000, gap=3.0, bid_pressure=0.5, spread=0.8, delta_iev=-40_000)
    )
    assert build > missing
    assert fade < missing


def test_cascade_rationale_mentions_delta_iev():
    auction = _auction(delta_iev=40_000)
    resp = evaluate_pre_open_signal_cascade(
        PreOpenSignalEvidenceBundle(auction_ncp=auction, open_viability=None),
        snapshot_date=date(2026, 6, 18),
    )
    assert resp is not None
    assert any("delta_iev=" in r for r in resp.assessment.rationale)


def test_builder_passes_delta_iev():
    candidate = SimpleNamespace(
        ticker="BBRI",
        iev=250_000,
        prev_close=Decimal("5000"),
        gap_pct=Decimal("1.2"),
        iep=5060,
        iep_gap_pct=Decimal("1.2"),
        bid_gap_pct=Decimal("0.8"),
        gap_price_source="IEP",
        bid_offer_imbalance=0.62,
        spread_pct=Decimal("0.4"),
        trend_signal="BULLISH",
        unusual_volume=False,
        iev_intensity=2.0,
        atr=Decimal("50"),
        rsi=Decimal("55"),
    )
    builder = PreOpenSignalInputsBuilder()
    without = builder.evaluate(
        candidate,
        trade_date=date(2026, 6, 18),
        delta_iev=None,
        **_ncp_kwargs(),
    )
    with_delta = builder.evaluate(
        candidate,
        trade_date=date(2026, 6, 18),
        delta_iev=80_000,
        **_ncp_kwargs(),
    )
    assert without is not None and with_delta is not None
    assert with_delta.score >= without.score
    bundle = builder.build_bundle(
        candidate,
        trade_date=date(2026, 6, 18),
        delta_iev=12_345,
        **_ncp_kwargs(),
    )
    assert bundle.auction_ncp is not None
    assert bundle.auction_ncp.delta_iev == 12_345
    assert bundle.auction_ncp.iep == 5060
    assert bundle.auction_ncp.iep_gap_pct == Decimal("1.2")
    assert bundle.auction_ncp.bid_gap_pct == Decimal("0.8")
    assert bundle.auction_ncp.gap_price_source == "IEP"


def test_builder_from_candidate_and_evaluate():
    candidate = SimpleNamespace(
        ticker="BBRI",
        iev=250_000,
        prev_close=Decimal("5000"),
        gap_pct=Decimal("1.2"),
        iep=5060,
        iep_gap_pct=Decimal("1.2"),
        bid_gap_pct=Decimal("0.8"),
        gap_price_source="IEP",
        bid_offer_imbalance=0.62,
        spread_pct=Decimal("0.4"),
        trend_signal="BULLISH",
        unusual_volume=False,
        iev_intensity=2.0,
        atr=Decimal("50"),
        rsi=Decimal("55"),
    )
    builder = PreOpenSignalInputsBuilder()
    resp = builder.evaluate(candidate, trade_date=date(2026, 6, 18), **_ncp_kwargs())
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
        candidate, trade_date=date(2026, 6, 18), **_ncp_kwargs()
    )
    assert bundle.auction_ncp is None
    assert evaluate_pre_open_signal_cascade(bundle, snapshot_date=date(2026, 6, 18)) is None


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
    bundle = PreOpenSignalEvidenceBundle(auction_ncp=None, open_viability=viability)
    assert evaluate_pre_open_signal_cascade(bundle, snapshot_date=date(2026, 6, 18)) is None


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
