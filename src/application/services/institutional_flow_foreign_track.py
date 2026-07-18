"""Foreign institutional track calculation logic."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

from src.application.services.institutional_flow_broker_metrics import (
    _Unavailable,
    foreign_flows,
    vwap_distance,
)
from src.application.services.institutional_flow_config import InstitutionalAccumulationConfig
from src.application.services.institutional_flow_math import (
    _clamp01,
    _group_by_date,
    _mean,
    _slope,
)
from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    ForeignFlowPoint,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import (
    EvidenceStatus,
    ForeignInstitutionalTrack,
)

if TYPE_CHECKING:
    from src.application.services.institutional_accumulation_evidence_builder import (
        InstitutionalAccumulationEvidenceRequest,
    )


def _foreign_participation(summaries: tuple[BrokerSummary, ...]) -> float | None:
    if not summaries:
        raise _Unavailable("no_broker_summaries")
    latest = max(summaries, key=lambda s: s.date)
    total = latest.total_value
    if total == Decimal("0"):
        raise _Unavailable("zero_total_value")
    ratio = float((latest.foreign_buy_value + latest.foreign_sell_value) / total)
    return _clamp01(ratio)


def _foreign_concentration(
    flows: list[BrokerDailyFlow],
    foreign_codes: frozenset[str],
) -> tuple[float | None, float | None]:
    foreign = foreign_flows(flows, foreign_codes)
    if not foreign:
        raise _Unavailable("no_foreign_flows")
    by_date = _group_by_date(foreign)
    recent = sorted(by_date)[-5:] or sorted(by_date)[-1:]
    cr4s: list[float] = []
    cr8s: list[float] = []
    for d in recent:
        session = by_date[d]
        total = sum(float(f.buy_value) for f in session)
        if total <= 0:
            continue
        buys = sorted((float(f.buy_value) for f in session), reverse=True)
        cr4s.append(_clamp01(sum(buys[:4]) / total))
        cr8s.append(_clamp01(sum(buys[:8]) / total))
    if not cr4s:
        raise _Unavailable("zero_foreign_buy_value")
    return _clamp01(_mean(cr4s)), _clamp01(_mean(cr8s))


def _cnfb_bullish(
    points: tuple[ForeignFlowPoint, ...],
    candles: list[Candle],
    config: InstitutionalAccumulationConfig,
    metadata: dict[str, Any],
) -> float | None:
    scores: list[float] = []
    per_window: dict[str, float] = {}
    for window in config.cnfb_bullish_windows:
        threshold = config.min_sessions.get(f"cnfb_{window}d", window)
        score = _cnfb_divergence(
            points, candles, window, threshold, bearish=False
        )
        if score is not None:
            scores.append(score)
            per_window[f"cnfb_{window}d"] = round(score, 4)
    if per_window:
        metadata["cnfb_bullish_scores"] = per_window
    if not scores:
        raise _Unavailable("insufficient_cnfb_sessions")
    return _clamp01(_mean(scores))


def _cnfb_bearish(
    points: tuple[ForeignFlowPoint, ...],
    candles: list[Candle],
    config: InstitutionalAccumulationConfig,
    metadata: dict[str, Any],
) -> float | None:
    per_window: dict[str, float] = {}
    for window in config.cnfb_bearish_windows:
        threshold = config.min_sessions.get(f"cnfb_{window}d", 2)
        score = _cnfb_divergence(
            points, candles, window, threshold, bearish=True
        )
        if score is not None:
            per_window[f"cnfb_{window}d"] = round(score, 4)
    if "cnfb_3d" in per_window:
        metadata["cnfb_distribution_3d"] = per_window["cnfb_3d"]
    if per_window:
        metadata["cnfb_bearish_scores"] = per_window
    if not per_window:
        raise _Unavailable("insufficient_fast_cnfb_sessions")
    # Diagnostic fingerprint only; not part of a track score slot.
    return per_window.get("cnfb_3d")


def _cnfb_divergence(
    points: tuple[ForeignFlowPoint, ...],
    candles: list[Candle],
    window: int,
    threshold: int,
    *,
    bearish: bool,
) -> float | None:
    ordered = sorted(points, key=lambda p: p.date)[-window:]
    if len(ordered) < threshold:
        return None
    close_by_date = {c.date: float(c.close) for c in candles}
    cnfb: list[float] = []
    prices: list[float] = []
    running = 0.0
    for point in ordered:
        running += float(point.net_val)
        if point.date not in close_by_date:
            continue
        cnfb.append(running)
        prices.append(close_by_date[point.date])
    if len(cnfb) < threshold or len(prices) < 2:
        return None
    cnfb_slope = _slope(cnfb)
    price_slope = _slope(prices)
    if bearish:
        return _bearish_score(cnfb_slope, price_slope)
    return _bullish_score(cnfb_slope, price_slope)


def _bullish_score(cnfb_slope: float, price_slope: float) -> float:
    if cnfb_slope > 0 and price_slope <= 0:
        return 1.0
    if cnfb_slope > 0 and price_slope > 0:
        return 0.5
    if cnfb_slope < 0 and price_slope < 0:
        return 0.2
    if cnfb_slope < 0 and price_slope >= 0:
        return 0.0
    return 0.2


def _bearish_score(cnfb_slope: float, price_slope: float) -> float:
    if cnfb_slope < 0 and price_slope >= 0:
        return 1.0
    if cnfb_slope > 0 and price_slope <= 0:
        return 0.0
    if cnfb_slope != 0:
        return 0.5
    return 0.5


def _foreign_vwap_distance(
    flows: list[BrokerDailyFlow],
    candles: list[Candle],
    config: InstitutionalAccumulationConfig,
    foreign_codes: frozenset[str],
) -> float | None:
    foreign = foreign_flows(flows, foreign_codes)
    threshold = config.min_sessions.get("vwap_20d", 10)
    return vwap_distance(
        foreign, candles, config.foreign_vwap_days, threshold
    )


def build_foreign_track(
    *,
    request: InstitutionalAccumulationEvidenceRequest,
    config: InstitutionalAccumulationConfig,
    foreign_codes: frozenset[str],
    candles: list[Candle],
    metadata: dict[str, Any],
    safe: Callable[[Callable[[], float | None], str], float | None],
    safe_pair: Callable[
        [Callable[[], tuple[float | None, float | None]], str],
        tuple[float | None, float | None]
    ],
    mean_available: Callable[[list[float | None]], float | None],
    unavailable: list[str],
) -> ForeignInstitutionalTrack:
    flows = list(request.broker_daily_flows)

    participation = safe(
        lambda: _foreign_participation(request.broker_summaries),
        "foreign_participation",
    )
    cr4, cr8 = safe_pair(
        lambda: _foreign_concentration(flows, foreign_codes),
        "foreign_concentration",
    )
    cnfb_score = safe(
        lambda: _cnfb_bullish(
            request.foreign_flow_points, candles, config, metadata
        ),
        "cnfb_divergence",
    )
    # Fast-distribution windows are diagnostic-only fingerprint data.
    safe(
        lambda: _cnfb_bearish(
            request.foreign_flow_points, candles, config, metadata
        ),
        "cnfb_distribution",
    )
    vwap_dist = safe(
        lambda: _foreign_vwap_distance(flows, candles, config, foreign_codes),
        "foreign_vwap_distance",
    )

    # ----- coverage: 4 slots (participation, cr4|cr8, cnfb, vwap)
    slots = [
        participation is not None,
        (cr4 is not None or cr8 is not None),
        cnfb_score is not None,
        vwap_dist is not None,
    ]
    coverage = round(sum(1 for s in slots if s) / len(slots), 4)

    # ----- conviction: renormalized weighted sum over AVAILABLE components
    w = config.foreign_track_weights
    concentration_score = mean_available([cr4, cr8])
    available: list[tuple[float, float]] = []  # (score, weight)
    if participation is not None:
        available.append((participation, w.get("foreign_participation", 0.0)))
    if concentration_score is not None:
        available.append(
            (concentration_score, w.get("foreign_concentration_cr4_cr8", 0.0))
        )
    if cnfb_score is not None:
        available.append((cnfb_score, w.get("cnfb_price_divergence", 0.0)))
    if vwap_dist is not None:
        available.append((vwap_dist, w.get("foreign_vwap_distance", 0.0)))
    total_w = sum(wt for _, wt in available)
    conviction = (
        sum(s * wt for s, wt in available) / total_w if total_w > 0 else 0.0
    )

    return ForeignInstitutionalTrack(
        foreign_participation_score=participation,
        foreign_cr4_score=cr4,
        foreign_cr8_score=cr8,
        cnfb_divergence_score=cnfb_score,
        foreign_vwap_distance_score=vwap_dist,
        coverage_score=_clamp01(coverage),
        conviction_score=_clamp01(round(conviction, 4)),
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=(),
        unavailable_reasons=tuple(unavailable),
    )
