"""Domestic bandar track calculation logic."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from src.application.services.institutional_flow_broker_metrics import (
    _net_by_broker,
    _top_brokers_by_net,
    _top_brokers_by_volume,
    _Unavailable,
    local_flows,
    vwap_distance_from_price,
)
from src.application.services.institutional_flow_config import InstitutionalAccumulationConfig
from src.application.services.institutional_flow_math import (
    _clamp01,
    _group_by_date,
    _slope,
)
from src.domain.entities.broker_flow import BrokerDailyFlow
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.institutional_accumulation_evidence import (
    DomesticBandarTrack,
    EvidenceStatus,
)

if TYPE_CHECKING:
    from src.application.services.institutional_accumulation_evidence_builder import (
        InstitutionalAccumulationEvidenceRequest,
    )


def _bandar_normalise(
    snapshot: BandarDetectorSnapshot | None,
    unavailable: list[str],
) -> tuple[float | None, float | None]:
    if snapshot is None:
        unavailable.append("bandar_snapshot_unavailable")
        return None, None
    try:
        broad = _clamp01((float(snapshot.broad_score) + 12.0) / 24.0)
        accum = _clamp01((float(snapshot.accumulation_score) + 6.0) / 12.0)
        return broad, accum
    except Exception as exc:
        unavailable.append(f"bandar_normalise_failed:{exc}")
        return None, None


def _broker_consistency(
    flows: list[BrokerDailyFlow],
    config: InstitutionalAccumulationConfig,
    foreign_codes: frozenset[str],
) -> float | None:
    local = local_flows(flows, foreign_codes)
    if not local:
        raise _Unavailable("no_local_flows")
    window = max(config.broker_consistency_days)
    by_date = _group_by_date(local)
    recent = sorted(by_date)[-window:]
    threshold = config.min_sessions.get("broker_consistency", 8)
    if len(recent) < threshold:
        raise _Unavailable("insufficient_consistency_sessions")
    top3 = _top_brokers_by_net(local, recent, count=3)
    if not top3:
        raise _Unavailable("no_top_brokers")
    aligned = 0
    for d in recent:
        net_by_broker = _net_by_broker(by_date[d])
        if all(net_by_broker.get(code, 0.0) > 0 for code in top3):
            aligned += 1
    return _clamp01(aligned / len(recent))


def _broker_reversal(
    flows: list[BrokerDailyFlow],
    config: InstitutionalAccumulationConfig,
    foreign_codes: frozenset[str],
) -> float | None:
    local = local_flows(flows, foreign_codes)
    if not local:
        raise _Unavailable("no_local_flows")
    window = min(config.broker_consistency_days)
    by_date = _group_by_date(local)
    recent = sorted(by_date)[-window:]
    if len(recent) < 5:
        raise _Unavailable("insufficient_reversal_sessions")
    half = len(recent) // 2
    early_dates = set(recent[:half])
    late_dates = set(recent[half:])
    top10 = _top_brokers_by_volume(local, recent, count=10)
    if not top10:
        raise _Unavailable("no_top_brokers")
    early_net: dict[str, float] = {}
    late_net: dict[str, float] = {}
    for d in recent:
        for flow in by_date[d]:
            code = flow.broker_code.upper()
            if code not in top10:
                continue
            if d in early_dates:
                early_net[code] = early_net.get(code, 0.0) + float(flow.net_value)
            elif d in late_dates:
                late_net[code] = late_net.get(code, 0.0) + float(flow.net_value)
    flipped = sum(
        1
        for code in top10
        if early_net.get(code, 0.0) < 0 and late_net.get(code, 0.0) > 0
    )
    return _clamp01(flipped / len(top10))


def _accumulation_session_ratio(
    flows: list[BrokerDailyFlow],
    config: InstitutionalAccumulationConfig,
    foreign_codes: frozenset[str],
) -> float | None:
    local = local_flows(flows, foreign_codes)
    if not local:
        raise _Unavailable("no_local_flows")
    window = max(config.broker_consistency_days)
    by_date = _group_by_date(local)
    recent = sorted(by_date)[-window:]
    if not recent:
        raise _Unavailable("no_sessions")
    top3 = _top_brokers_by_net(local, recent, count=3)
    if not top3:
        raise _Unavailable("no_top_brokers")
    buying_sessions = 0
    for d in recent:
        net_by_broker = _net_by_broker(by_date[d])
        collective = sum(net_by_broker.get(code, 0.0) for code in top3)
        if collective > 0:
            buying_sessions += 1
    return _clamp01(buying_sessions / len(recent))


def _domestic_vwap_distance(
    flows: list[BrokerDailyFlow],
    current_price: float | None,
    config: InstitutionalAccumulationConfig,
    foreign_codes: frozenset[str],
) -> float | None:
    local = local_flows(flows, foreign_codes)
    threshold = config.min_sessions.get("vwap_20d", 10)
    return vwap_distance_from_price(
        local, current_price, config.domestic_vwap_days, threshold
    )


def _broker_hhi_divergence(flows: list[BrokerDailyFlow]) -> float | None:
    by_date = _group_by_date(flows)
    recent = sorted(by_date)[-5:]
    if len(recent) < 3:
        raise _Unavailable("insufficient_hhi_sessions")
    buy_hhi: list[float] = []
    sell_hhi: list[float] = []
    for d in recent:
        session = by_date[d]
        total_buy = sum(float(f.buy_value) for f in session)
        total_sell = sum(float(f.sell_value) for f in session)
        if total_buy > 0:
            buy_hhi.append(
                sum((float(f.buy_value) / total_buy) ** 2 for f in session)
            )
        if total_sell > 0:
            sell_hhi.append(
                sum((float(f.sell_value) / total_sell) ** 2 for f in session)
            )
    if len(buy_hhi) < 3 or len(sell_hhi) < 3:
        raise _Unavailable("insufficient_hhi_sides")
    buy_slope = _slope(buy_hhi)
    sell_slope = _slope(sell_hhi)
    if buy_slope > 0 and sell_slope <= 0:
        return 1.0
    if buy_slope > 0 and sell_slope > 0:
        return 0.5
    return 0.0


def build_domestic_track(
    *,
    request: InstitutionalAccumulationEvidenceRequest,
    config: InstitutionalAccumulationConfig,
    foreign_codes: frozenset[str],
    current_price: float | None,
    safe: Callable[[Callable[[], float | None], str], float | None],
    mean_available: Callable[[list[float | None]], float | None],
    unavailable: list[str],
) -> DomesticBandarTrack:
    flows = list(request.broker_daily_flows)

    consistency = safe(
        lambda: _broker_consistency(flows, config, foreign_codes),
        "broker_consistency",
    )
    reversal = safe(
        lambda: _broker_reversal(flows, config, foreign_codes),
        "broker_reversal",
    )
    session_ratio = safe(
        lambda: _accumulation_session_ratio(flows, config, foreign_codes),
        "accumulation_session_ratio",
    )
    vwap_dist = safe(
        lambda: _domestic_vwap_distance(flows, current_price, config, foreign_codes),
        "domestic_buy_vwap_distance",
    )
    hhi_div = safe(
        lambda: _broker_hhi_divergence(flows),
        "broker_hhi_divergence",
    )
    broad_norm, accum_norm = _bandar_normalise(
        request.bandar_snapshot, unavailable
    )

    # ----- coverage: 6 slots (bandar broad|accumulation collapse to 1)
    slots = [
        consistency is not None,
        reversal is not None,
        session_ratio is not None,
        vwap_dist is not None,
        hhi_div is not None,
        (broad_norm is not None or accum_norm is not None),
    ]
    coverage = round(sum(1 for s in slots if s) / len(slots), 4)

    # ----- conviction: renormalized weighted sum over AVAILABLE components
    w = config.domestic_track_weights
    bandar_score = mean_available([broad_norm, accum_norm])
    available: list[tuple[float, float]] = []
    if consistency is not None:
        available.append((consistency, w.get("broker_consistency", 0.0)))
    if reversal is not None:
        available.append((reversal, w.get("broker_reversal", 0.0)))
    if session_ratio is not None:
        available.append(
            (session_ratio, w.get("accumulation_session_ratio", 0.0))
        )
    if vwap_dist is not None:
        available.append((vwap_dist, w.get("domestic_buy_vwap_distance", 0.0)))
    if hhi_div is not None:
        available.append((hhi_div, w.get("broker_hhi_divergence", 0.0)))
    if bandar_score is not None:
        available.append(
            (bandar_score, w.get("bandar_broad_or_accumulation_score", 0.0))
        )
    total_w = sum(wt for _, wt in available)
    conviction = (
        sum(s * wt for s, wt in available) / total_w if total_w > 0 else 0.0
    )

    return DomesticBandarTrack(
        broker_consistency_score=consistency,
        broker_reversal_score=reversal,
        accumulation_session_ratio=session_ratio,
        domestic_buy_vwap_distance_score=vwap_dist,
        broker_hhi_divergence_score=hhi_div,
        bandar_broad_score_normalized=broad_norm,
        bandar_accumulation_score_normalized=accum_norm,
        coverage_score=_clamp01(coverage),
        conviction_score=_clamp01(round(conviction, 4)),
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        reasons=(),
        unavailable_reasons=tuple(unavailable),
    )
