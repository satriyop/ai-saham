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
    intensity=2.0,
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


def test_aligned_up_iep_and_buy_pressure_is_bullish_high_confidence():
    result = _evaluate()

    assert result.direction is PreOpenDirection.BULLISH
    assert result.confidence is PreOpenDirectionConfidence.HIGH
    assert result.auction_quality is PreOpenAuctionQuality.RELIABLE
    assert result.raw_score == 80


def test_aligned_down_iep_and_sell_pressure_is_bearish():
    result = _evaluate(iep=990, pressure=0.35)

    assert result.direction is PreOpenDirection.BEARISH
    assert result.raw_score == 20


def test_opposing_iep_and_pressure_is_conflicted():
    result = _evaluate(iep=1010, pressure=0.35)

    assert result.direction is PreOpenDirection.CONFLICTED
    assert result.raw_score == 35


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
    assert result.raw_score == 0


def test_missing_delta_is_low_confidence_and_caution():
    result = _evaluate(delta_iev=None)

    assert result.confidence is PreOpenDirectionConfidence.LOW
    assert result.auction_quality is PreOpenAuctionQuality.CAUTION
    assert result.raw_score == 55


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
