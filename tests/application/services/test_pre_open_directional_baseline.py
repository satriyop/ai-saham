"""Pre-open directional baseline v2 continuous ranking tests."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from src.application.services.pre_open_directional_baseline import (
    evaluate_pre_open_directional_baseline,
)
from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
)
from src.domain.value_objects.idx_market import IDX_TIMEZONE
from src.domain.value_objects.pre_open_directional_baseline import (
    PRE_OPEN_DIRECTIONAL_BASELINE_CONTRACT,
    PreOpenAuctionQuality,
    PreOpenDirection,
    PreOpenDirectionConfidence,
)
from src.domain.value_objects.pre_open_signal_evidence import (
    AuctionNcpEvidence,
    AuctionNcpProvenance,
    OpenViabilityEvidence,
    PreOpenSignalEvidenceBundle,
)

DAY = date(2026, 7, 27)


def _bundle(
    *,
    iep=1010,
    prev_close=Decimal("1000"),
    pressure=0.65,
    spread=Decimal("0.50"),
    final_iev=540_000,
    delta_iev=40_000,
    intensity=0.05,
    rsi_extension=False,
    unusual_volume=False,
):
    provenance = AuctionNcpProvenance(
        ticker="BBCA",
        collection_started_at=datetime(2026, 7, 27, 8, 57, tzinfo=IDX_TIMEZONE),
        decision_at=datetime(2026, 7, 27, 8, 57, 30, tzinfo=IDX_TIMEZONE),
        capture_phase="NCP_LOCKED",
        source_is_live=True,
        snapshot_ref="live:2026-07-27T08:57:30+07:00",
        trade_date=DAY,
    )
    iep_gap = (
        ((Decimal(iep) - prev_close) / prev_close * 100).quantize(Decimal("0.01"))
        if iep is not None
        else None
    )
    auction = AuctionNcpEvidence(
        ticker="BBCA",
        iev=final_iev,
        gap_pct=iep_gap,
        bid_pressure=pressure,
        spread_pct=spread,
        prev_close=prev_close,
        provenance=provenance,
        iep=iep,
        iep_gap_pct=iep_gap,
        gap_price_source="IEP" if iep is not None else None,
        delta_iev=delta_iev,
    )
    viability = OpenViabilityEvidence(
        ticker="BBCA",
        gap_out=False,
        friction_fail=False,
        unusual_volume=unusual_volume,
        rsi_extension=rsi_extension,
        trend_signal=None,
        iev_intensity=intensity,
        atr=Decimal("20"),
        gap_pct=iep_gap,
    )
    return PreOpenSignalEvidenceBundle(
        auction_ncp=auction,
        open_viability=viability,
    )


def _evaluate(**kwargs):
    return evaluate_pre_open_directional_baseline(
        _bundle(**kwargs),
        config=PreOpenDirectionalBaselineConfig(),
    )


def test_contract_is_v2():
    result = _evaluate()
    assert result.contract == PRE_OPEN_DIRECTIONAL_BASELINE_CONTRACT
    assert result.contract.endswith(".v2")


def test_aligned_up_iep_and_buy_pressure_is_bullish():
    result = _evaluate()
    assert result.direction is PreOpenDirection.BULLISH
    assert result.auction_quality is PreOpenAuctionQuality.RELIABLE
    assert 50.0 < result.raw_score <= 100.0


def test_aligned_down_iep_and_sell_pressure_is_bearish():
    result = _evaluate(iep=990, pressure=0.35)
    assert result.direction is PreOpenDirection.BEARISH
    assert result.raw_score < 45.0


def test_opposing_iep_and_pressure_is_conflicted():
    result = _evaluate(iep=1010, pressure=0.35)
    assert result.direction is PreOpenDirection.CONFLICTED
    assert 20.0 < result.raw_score < 50.0


def test_one_tick_boundary_is_directional_and_inside_tick_is_flat():
    up = _evaluate(iep=1005)
    flat = _evaluate(iep=1004)
    assert up.factors.iep_direction == "UP"
    assert flat.factors.iep_direction == "FLAT"
    assert flat.direction is PreOpenDirection.NEUTRAL


def test_pressure_boundaries_are_inclusive():
    assert _evaluate(pressure=0.60).factors.book_pressure_state == "BUY"
    assert _evaluate(pressure=0.40).factors.book_pressure_state == "SELL"


def test_missing_required_direction_leg_is_unknown_and_unreliable():
    result = _evaluate(iep=None)
    assert result.direction is PreOpenDirection.UNKNOWN
    assert result.auction_quality is PreOpenAuctionQuality.UNRELIABLE
    assert result.raw_score == 0.0


def test_missing_delta_is_low_confidence_and_caution():
    result = _evaluate(delta_iev=None)
    assert result.confidence is PreOpenDirectionConfidence.LOW
    assert result.auction_quality is PreOpenAuctionQuality.CAUTION
    assert result.raw_score > 0.0


def test_live_scale_intensity_does_not_force_low_when_delta_builds():
    """Corpus intensities are ~0.02; high delta still earns HIGH/MEDIUM confidence."""
    result = _evaluate(intensity=0.05, final_iev=540_000, delta_iev=40_000)
    assert result.direction is PreOpenDirection.BULLISH
    assert result.confidence is PreOpenDirectionConfidence.HIGH
    assert result.raw_score > 55.0


def test_score_monotonic_in_pressure_for_bullish():
    low_p = _evaluate(pressure=0.60, intensity=0.05)
    high_p = _evaluate(pressure=0.90, intensity=0.05)
    assert low_p.direction is PreOpenDirection.BULLISH
    assert high_p.direction is PreOpenDirection.BULLISH
    assert high_p.raw_score >= low_p.raw_score


def test_score_monotonic_in_delta_ratio_for_bullish():
    low_d = _evaluate(final_iev=500_000, delta_iev=5_000, intensity=0.05)  # ratio ~0.01
    high_d = _evaluate(final_iev=500_000, delta_iev=80_000, intensity=0.05)  # ratio ~0.19
    assert low_d.direction is PreOpenDirection.BULLISH
    assert high_d.direction is PreOpenDirection.BULLISH
    assert high_d.raw_score >= low_d.raw_score


def test_score_is_continuous_not_six_value_table():
    scores = {
        _evaluate(pressure=p, final_iev=520_000, delta_iev=d, intensity=i).raw_score
        for p, d, i in (
            (0.62, 10_000, 0.01),
            (0.70, 25_000, 0.03),
            (0.80, 40_000, 0.05),
            (0.90, 60_000, 0.08),
            (0.65, 15_000, 0.02),
            (0.75, 35_000, 0.04),
        )
    }
    # Six-value table had only 6 ints; continuous board must not collapse.
    assert len(scores) >= 5
    assert not scores <= {0, 20, 35, 45, 55, 70, 80}


def test_fading_iev_reduces_confidence_without_changing_direction():
    result = _evaluate(final_iev=450_000, delta_iev=-50_000)
    assert result.direction is PreOpenDirection.BULLISH
    assert result.confidence is PreOpenDirectionConfidence.LOW
    assert result.factors.participation_state == "FADING"


def test_large_gap_is_caution_not_unreliable():
    result = _evaluate(iep=1060)
    assert result.auction_quality is PreOpenAuctionQuality.CAUTION
    assert "large_gap" in result.quality_reasons


def test_unusable_spread_is_unreliable():
    result = _evaluate(spread=Decimal("1.51"))
    assert result.auction_quality is PreOpenAuctionQuality.UNRELIABLE
    assert "spread_unusable" in result.quality_reasons


def test_rsi_and_unusual_volume_are_context_only():
    ordinary = _evaluate()
    contextual = _evaluate(rsi_extension=True, unusual_volume=True)
    assert contextual.direction is ordinary.direction
    assert contextual.confidence is ordinary.confidence
    assert contextual.auction_quality is ordinary.auction_quality
    assert contextual.raw_score == ordinary.raw_score


def test_spread_quality_does_not_change_raw_score():
    """Auction quality labels do not enter the continuous ranking formula."""
    reliable = _evaluate(spread=Decimal("0.50"), iep=1010)
    caution = _evaluate(spread=Decimal("1.20"), iep=1010)
    assert reliable.raw_score == caution.raw_score
    assert reliable.auction_quality is PreOpenAuctionQuality.RELIABLE
    assert caution.auction_quality is PreOpenAuctionQuality.CAUTION
