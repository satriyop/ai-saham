"""Pure deterministic pre-open directional baseline policy.

Layer: Application

Contract ``pre_open_directional_baseline.v2``: discrete direction labels are
unchanged; ranking ``raw_score`` is continuous in book pressure, delta IEV
ratio, and IEV intensity (no unreachable intensity boolean clamp).
"""

from __future__ import annotations

import math
from decimal import Decimal

from src.application.services.signal_engine_config import (
    PreOpenDirectionalBaselineConfig,
)
from src.domain.value_objects.pre_open_directional_baseline import (
    PRE_OPEN_DIRECTIONAL_BASELINE_CONTRACT,
    PreOpenAuctionQuality,
    PreOpenBaselineAssessment,
    PreOpenBaselineFactors,
    PreOpenDirection,
    PreOpenDirectionConfidence,
)
from src.domain.value_objects.pre_open_signal_evidence import (
    PreOpenSignalEvidenceBundle,
)
from src.domain.value_objects.tick_size import idx_tick_size


def evaluate_pre_open_directional_baseline(
    bundle: PreOpenSignalEvidenceBundle,
    *,
    config: PreOpenDirectionalBaselineConfig,
) -> PreOpenBaselineAssessment | None:
    """Return the canonical long-only baseline, or None without NCP evidence."""
    auction = bundle.auction_ncp
    if auction is None:
        return None

    viability = bundle.open_viability
    iep_direction = _iep_direction(
        iep=auction.iep,
        previous_close=auction.prev_close,
    )
    pressure_state = _book_pressure_state(
        auction.bid_pressure,
        config=config,
    )
    direction = _combine_direction(iep_direction, pressure_state)
    delta_ratio = _delta_ratio(auction.iev, auction.delta_iev)
    participation_state = _participation_state(delta_ratio, config=config)
    intensity = viability.iev_intensity if viability is not None else None
    confidence = _confidence(
        delta_ratio=delta_ratio,
        iev_intensity=intensity,
        config=config,
    )
    quality, quality_reasons = _auction_quality(
        auction=auction,
        iev_intensity=intensity,
        delta_ratio=delta_ratio,
        config=config,
    )
    raw_score = _continuous_raw_score(
        direction,
        delta_ratio=delta_ratio,
        pressure=auction.bid_pressure,
        intensity=intensity,
        config=config,
    )
    factors = PreOpenBaselineFactors(
        iep_direction=iep_direction,
        book_pressure_state=pressure_state,
        participation_state=participation_state,
        iep_gap_pct=(float(auction.iep_gap_pct) if auction.iep_gap_pct is not None else None),
        book_pressure=auction.bid_pressure,
        delta_iev=auction.delta_iev,
        delta_iev_ratio=delta_ratio,
        iev_intensity=intensity,
        spread_pct=(float(auction.spread_pct) if auction.spread_pct is not None else None),
        rsi_extension=bool(viability.rsi_extension) if viability is not None else False,
        unusual_volume=bool(viability.unusual_volume) if viability is not None else False,
    )
    rationale = (
        f"direction={direction.value}",
        f"confidence={confidence.value}",
        f"auction_quality={quality.value}",
        f"iep_direction={iep_direction}",
        f"book_pressure={pressure_state}",
        f"participation={participation_state}",
        f"raw_score={raw_score:.4f}",
    )
    return PreOpenBaselineAssessment(
        contract=PRE_OPEN_DIRECTIONAL_BASELINE_CONTRACT,
        direction=direction,
        confidence=confidence,
        auction_quality=quality,
        raw_score=raw_score,
        factors=factors,
        rationale=rationale,
        quality_reasons=quality_reasons,
    )


def _iep_direction(*, iep: int | None, previous_close: Decimal | None) -> str:
    if iep is None or previous_close is None or previous_close <= 0:
        return "UNKNOWN"
    tick = idx_tick_size(previous_close)
    price = Decimal(iep)
    if price >= previous_close + tick:
        return "UP"
    if price <= previous_close - tick:
        return "DOWN"
    return "FLAT"


def _book_pressure_state(
    pressure: float | None,
    *,
    config: PreOpenDirectionalBaselineConfig,
) -> str:
    if pressure is None:
        return "UNKNOWN"
    if pressure >= config.buy_pressure_min:
        return "BUY"
    if pressure <= config.sell_pressure_max:
        return "SELL"
    return "BALANCED"


def _combine_direction(iep_direction: str, pressure_state: str) -> PreOpenDirection:
    if "UNKNOWN" in (iep_direction, pressure_state):
        return PreOpenDirection.UNKNOWN
    if iep_direction == "UP" and pressure_state == "BUY":
        return PreOpenDirection.BULLISH
    if iep_direction == "DOWN" and pressure_state == "SELL":
        return PreOpenDirection.BEARISH
    if (iep_direction, pressure_state) in (("UP", "SELL"), ("DOWN", "BUY")):
        return PreOpenDirection.CONFLICTED
    return PreOpenDirection.NEUTRAL


def _delta_ratio(final_iev: int, delta_iev: int | None) -> float | None:
    if delta_iev is None:
        return None
    baseline = final_iev - delta_iev
    if baseline <= 0:
        return None
    return float(delta_iev) / float(baseline)


def _participation_state(
    delta_ratio: float | None,
    *,
    config: PreOpenDirectionalBaselineConfig,
) -> str:
    if delta_ratio is None:
        return "MISSING"
    if delta_ratio >= config.high_confidence_build_min:
        return "BUILDING"
    if delta_ratio < config.medium_confidence_floor:
        return "FADING"
    return "STABLE"


def _confidence(
    *,
    delta_ratio: float | None,
    iev_intensity: float | None,
    config: PreOpenDirectionalBaselineConfig,
) -> PreOpenDirectionConfidence:
    """Display confidence from delta_ratio; intensity uses a live-scale soft floor.

    Does **not** force LOW solely because intensity &lt; 1.0 (unreachable on current
    corpus scale). Missing delta still yields LOW.
    """
    if delta_ratio is None:
        return PreOpenDirectionConfidence.LOW
    if delta_ratio >= config.high_confidence_build_min:
        if iev_intensity is None or iev_intensity >= config.intensity_high_soft:
            return PreOpenDirectionConfidence.HIGH
        return PreOpenDirectionConfidence.MEDIUM
    if delta_ratio >= config.medium_confidence_floor:
        return PreOpenDirectionConfidence.MEDIUM
    return PreOpenDirectionConfidence.LOW


def _auction_quality(
    *,
    auction,
    iev_intensity: float | None,
    delta_ratio: float | None,
    config: PreOpenDirectionalBaselineConfig,
) -> tuple[PreOpenAuctionQuality, tuple[str, ...]]:
    unreliable: list[str] = []
    caution: list[str] = []
    if auction.iep is None or auction.iep_gap_pct is None:
        unreliable.append("iep_missing")
    if auction.bid_pressure is None:
        unreliable.append("book_pressure_missing")
    if auction.spread_pct is None:
        unreliable.append("spread_missing")
    elif float(auction.spread_pct) > config.max_spread_pct:
        unreliable.append("spread_unusable")
    elif float(auction.spread_pct) > config.reliable_spread_max_pct:
        caution.append("spread_wide")
    if (
        auction.iep_gap_pct is not None
        and abs(float(auction.iep_gap_pct)) > config.large_gap_caution_pct
    ):
        caution.append("large_gap")
    if delta_ratio is None:
        caution.append("delta_iev_missing")
    elif delta_ratio < config.medium_confidence_floor:
        caution.append("iev_fading")
    if iev_intensity is None:
        caution.append("iev_intensity_missing")
    if unreliable:
        return PreOpenAuctionQuality.UNRELIABLE, tuple(unreliable + caution)
    if caution:
        return PreOpenAuctionQuality.CAUTION, tuple(caution)
    return PreOpenAuctionQuality.RELIABLE, ()


def _continuous_raw_score(
    direction: PreOpenDirection,
    *,
    delta_ratio: float | None,
    pressure: float | None,
    intensity: float | None,
    config: PreOpenDirectionalBaselineConfig,
) -> float:
    """Continuous long-only ranking score in [0, 100].

    Monotonic (direction held fixed to BULLISH): higher ``pressure`` and higher
    ``delta_iev_ratio`` do not decrease the score. Intensity contributes via
    log1p on the live scale (``intensity_scale`` ≈ corpus median).
    """
    if direction is PreOpenDirection.UNKNOWN:
        return 0.0

    p = 0.5 if pressure is None else float(pressure)
    d = 0.0 if delta_ratio is None else float(delta_ratio)
    d = max(-config.delta_clamp, min(config.delta_clamp, d))
    i = 0.0 if intensity is None else max(0.0, float(intensity))

    pressure_feat = (p - 0.5) * 2.0  # roughly -1..1
    delta_feat = d / config.delta_clamp  # -1..1
    intensity_feat = min(math.log1p(i / config.intensity_scale) / 3.0, 1.0)

    attractiveness = (
        config.weight_pressure * pressure_feat
        + config.weight_delta * delta_feat
        + config.weight_intensity * intensity_feat
    )

    anchors = {
        PreOpenDirection.BULLISH: config.anchor_bullish,
        PreOpenDirection.NEUTRAL: config.anchor_neutral,
        PreOpenDirection.CONFLICTED: config.anchor_conflicted,
        PreOpenDirection.BEARISH: config.anchor_bearish,
    }
    base = anchors[direction]
    if direction is PreOpenDirection.BULLISH:
        score = base + attractiveness
    elif direction is PreOpenDirection.BEARISH:
        score = base + attractiveness
    elif direction is PreOpenDirection.CONFLICTED:
        score = base + 0.4 * attractiveness
    else:
        score = base + 0.5 * attractiveness

    return round(max(0.0, min(100.0, score)), 4)
