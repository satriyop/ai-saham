"""Tests for InstitutionalAccumulationEvidenceBuilder (Phase E, diagnostic-only)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.services.institutional_accumulation_evidence_builder import (
    InstitutionalAccumulationConfig,
    InstitutionalAccumulationEvidenceBuilder,
    InstitutionalAccumulationEvidenceRequest,
)
from src.domain.entities.broker_flow import (
    BrokerDailyFlow,
    BrokerSummary,
    ForeignFlowPoint,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.bandar_detector_snapshot import BandarDetectorSnapshot
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus

BASE = date(2026, 6, 1)
FOREIGN = "ZP"  # in DEFAULT_FOREIGN_BROKER_CODES
FOREIGN2 = "YU"
LOCAL = "PD"  # not foreign
LOCAL2 = "CC"
LOCAL3 = "NI"


def _d(offset: int) -> date:
    return BASE + timedelta(days=offset)


def _flow(
    code: str,
    offset: int,
    *,
    buy: float,
    sell: float,
    avg_buy: float = 100.0,
) -> BrokerDailyFlow:
    net = buy - sell
    return BrokerDailyFlow(
        ticker="TEST",
        broker_code=code,
        broker_name=code,
        date=_d(offset),
        buy_lot=int(buy),
        sell_lot=int(sell),
        net_lot=int(net),
        buy_value=Decimal(str(buy)),
        sell_value=Decimal(str(sell)),
        net_value=Decimal(str(net)),
        avg_buy_price=Decimal(str(avg_buy)),
        avg_sell_price=Decimal(str(avg_buy)),
        avg_price=Decimal(str(avg_buy)),
        buy_pct=0.0,
        sell_pct=0.0,
    )


def _summary(offset: int, *, fb: float, fs: float, total: float) -> BrokerSummary:
    return BrokerSummary(
        ticker="TEST",
        date=_d(offset),
        top_buyers=(),
        top_sellers=(),
        foreign_buy_value=Decimal(str(fb)),
        foreign_sell_value=Decimal(str(fs)),
        foreign_buy_lot=int(fb),
        foreign_sell_lot=int(fs),
        total_value=Decimal(str(total)),
        total_lot=int(total),
    )


def _ffp(offset: int, net_val: float) -> ForeignFlowPoint:
    return ForeignFlowPoint(
        ticker="TEST",
        date=_d(offset),
        net_val=Decimal(str(net_val)),
        net_lot=int(net_val),
        avg_price=Decimal("100"),
    )


def _candle(offset: int, close: float) -> Candle:
    return Candle(
        ticker="TEST",
        date=_d(offset),
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=1000,
    )


def _bandar(broad_today: str = "Big Acc") -> BandarDetectorSnapshot:
    return BandarDetectorSnapshot(
        ticker="TEST",
        session_date=_d(29),
        broker_accdist="Acc",
        today_accdist=broad_today,
        five_day_accdist=broad_today,
        top1_accdist=broad_today,
        top1_percent=10.0,
        today_percent=5.0,
        total_buyer=5,
        total_seller=3,
        top3_accdist=broad_today,
        top5_accdist=broad_today,
        top10_accdist=broad_today,
    )


def _request(**kwargs) -> InstitutionalAccumulationEvidenceRequest:
    defaults = dict(
        ticker="TEST",
        snapshot_date=_d(30),
        broker_daily_flows=(),
        foreign_flow_points=(),
        broker_summaries=(),
        bandar_snapshot=None,
        candles=(),
    )
    defaults.update(kwargs)
    return InstitutionalAccumulationEvidenceRequest(**defaults)  # type: ignore[arg-type]


def _builder() -> InstitutionalAccumulationEvidenceBuilder:
    return InstitutionalAccumulationEvidenceBuilder()


# --------------------------------------------------------------------------- #
# 1. Foreign track: CR4 / CR8
# --------------------------------------------------------------------------- #
def test_foreign_cr4_cr8_from_daily_flows():
    # Single foreign session, 5 brokers: one dominant -> high concentration.
    flows = tuple(
        _flow(code, 0, buy=v, sell=0.0)
        for code, v in [
            (FOREIGN, 100.0),
            (FOREIGN2, 10.0),
            ("AK", 5.0),
            ("BK", 3.0),
            ("CP", 2.0),
        ]
    )
    result = _builder().build(_request(broker_daily_flows=flows))
    track = result.foreign_institutional_track
    # top4 buy / total = (100+10+5+3)/120 = 0.9833
    assert track.foreign_cr4_score == pytest.approx(118 / 120, abs=1e-4)
    # all 5 brokers within top8 -> CR8 = 1.0
    assert track.foreign_cr8_score == pytest.approx(1.0, abs=1e-4)
    assert result.evidence_status is EvidenceStatus.DIAGNOSTIC
    assert result.metadata["diagnostic_only"] is True


# --------------------------------------------------------------------------- #
# 2. Domestic track: broker consistency + bandar normalisation
# --------------------------------------------------------------------------- #
def test_domestic_consistency_and_bandar_normalisation():
    # 10 sessions where 3 local brokers are always net buyers -> consistency 1.0
    flows = []
    for off in range(10):
        for code in (LOCAL, LOCAL2, LOCAL3):
            flows.append(_flow(code, off, buy=100.0, sell=10.0))
    result = _builder().build(
        _request(
            broker_daily_flows=tuple(flows),
            bandar_snapshot=_bandar("Big Acc"),
        )
    )
    track = result.domestic_bandar_track
    assert track.broker_consistency_score == pytest.approx(1.0, abs=1e-4)
    # broad_score with all six labels "Big Acc" (=2 each) = 12 -> (12+12)/24 = 1.0
    assert track.bandar_broad_score_normalized == pytest.approx(1.0, abs=1e-4)
    # accumulation_score = today+5d+top1 = 6 -> (6+6)/12 = 1.0
    assert track.bandar_accumulation_score_normalized == pytest.approx(1.0, abs=1e-4)


def test_missing_bandar_marks_reason_but_track_still_available():
    flows = []
    for off in range(10):
        for code in (LOCAL, LOCAL2, LOCAL3):
            flows.append(_flow(code, off, buy=100.0, sell=10.0))
    result = _builder().build(
        _request(broker_daily_flows=tuple(flows), bandar_snapshot=None)
    )
    track = result.domestic_bandar_track
    assert track.bandar_broad_score_normalized is None
    assert "bandar_snapshot_unavailable" in track.unavailable_reasons
    assert track.coverage_score > 0.0


# --------------------------------------------------------------------------- #
# 3. Counterparty HHI + UNAVAILABLE on zero denominator
# --------------------------------------------------------------------------- #
def test_counterparty_hhi_computed():
    # Concentrated buyer (one broker) vs diffuse sellers -> buy HHI > sell HHI.
    flows = [
        _flow(LOCAL, 0, buy=100.0, sell=0.0),  # net +100 buyer
        _flow(LOCAL2, 0, buy=0.0, sell=50.0),  # net -50 seller
        _flow(LOCAL3, 0, buy=0.0, sell=50.0),  # net -50 seller
    ]
    result = _builder().build(_request(broker_daily_flows=tuple(flows)))
    cp = result.counterparty_transfer
    assert cp is not None
    assert cp.buy_side_hhi == pytest.approx(1.0, abs=1e-6)  # single net buyer
    assert cp.sell_side_hhi == pytest.approx(0.5, abs=1e-6)  # two equal sellers
    # raw_asymmetry = 1.0 - 0.5 = 0.5 -> (0.5+1)/2 = 0.75
    assert cp.transfer_asymmetry_score == pytest.approx(0.75, abs=1e-4)


def test_counterparty_unavailable_on_zero_denominator():
    # All brokers are net buyers -> total_net_sell == 0 -> UNAVAILABLE.
    flows = [
        _flow(LOCAL, 0, buy=100.0, sell=0.0),
        _flow(LOCAL2, 0, buy=80.0, sell=0.0),
    ]
    result = _builder().build(_request(broker_daily_flows=tuple(flows)))
    cp = result.counterparty_transfer
    assert cp is not None
    assert cp.transfer_asymmetry_score is None
    assert cp.buy_side_hhi is None
    assert "zero_net_buy_or_sell" in cp.unavailable_reasons


# --------------------------------------------------------------------------- #
# 4. CNFB divergence: score 1.0 when CNFB positive, price flat
# --------------------------------------------------------------------------- #
def test_cnfb_divergence_positive_flow_flat_price_scores_one():
    # 20 sessions of steady positive foreign net flow, flat close.
    points = tuple(_ffp(off, 100.0) for off in range(20))
    candles = tuple(_candle(off, 500.0) for off in range(20))
    result = _builder().build(
        _request(foreign_flow_points=points, candles=candles)
    )
    track = result.foreign_institutional_track
    # cnfb slope > 0, price slope == 0 -> bullish score 1.0
    assert track.cnfb_divergence_score == pytest.approx(1.0, abs=1e-4)
    assert result.metadata["cnfb_bullish_scores"]["cnfb_20d"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 5. Below-minimum sessions -> metric None, coverage < 1.0
# --------------------------------------------------------------------------- #
def test_below_min_sessions_marks_metric_unavailable():
    # Only 5 CNFB points (< 15 min for 20d, < 22 for 30d) -> divergence None.
    points = tuple(_ffp(off, 100.0) for off in range(5))
    candles = tuple(_candle(off, 500.0) for off in range(5))
    result = _builder().build(
        _request(foreign_flow_points=points, candles=candles)
    )
    track = result.foreign_institutional_track
    assert track.cnfb_divergence_score is None
    assert track.coverage_score < 1.0
    assert any("cnfb_divergence" in r for r in track.unavailable_reasons)


# --------------------------------------------------------------------------- #
# 6. Missing foreign flows -> domestic track still has coverage
# --------------------------------------------------------------------------- #
def test_missing_foreign_flows_keeps_domestic_coverage():
    # Only local flows present; no foreign brokers, no foreign summaries.
    flows = []
    for off in range(10):
        for code in (LOCAL, LOCAL2, LOCAL3):
            flows.append(_flow(code, off, buy=100.0, sell=10.0))
    result = _builder().build(
        _request(broker_daily_flows=tuple(flows), bandar_snapshot=_bandar())
    )
    assert result.domestic_bandar_track.coverage_score > 0.0
    # foreign participation/concentration unavailable but doesn't kill domestic
    assert result.foreign_institutional_track.foreign_cr4_score is None


# --------------------------------------------------------------------------- #
# 7. Exception in sub-computation degrades gracefully, never raises
# --------------------------------------------------------------------------- #
def test_subcomputation_exception_degrades_without_raising():
    class Boom:
        broker_code = "PD"

        @property
        def date(self):  # noqa: A003 - mimic attribute for grouping
            raise RuntimeError("boom")

    # Malformed flow-like object; grouping/metrics should degrade, not raise.
    bad_flows = (Boom(),)
    result = _builder().build(_request(broker_daily_flows=bad_flows))  # type: ignore[arg-type]
    assert result.evidence_status is EvidenceStatus.DIAGNOSTIC
    assert result.metadata["diagnostic_only"] is True
    # Track metrics unavailable; no exception surfaced.
    assert result.domestic_bandar_track.broker_consistency_score is None


# --------------------------------------------------------------------------- #
# 8. Config weight validation
# --------------------------------------------------------------------------- #
def test_config_validation_rejects_bad_weight_sum():
    cfg = InstitutionalAccumulationConfig(
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        cnfb_bullish_windows=(20, 30),
        cnfb_bearish_windows=(3, 5, 7),
        foreign_vwap_days=20,
        domestic_vwap_days=20,
        broker_consistency_days=(10, 20),
        counterparty_window_days=5,
        min_sessions={},
        foreign_track_weights={"a": 0.5, "b": 0.4},  # sums to 0.9
        domestic_track_weights={"x": 1.0},
        track_weights={"foreign_institutional_track": 1.0},
    )
    with pytest.raises(ValueError):
        cfg.validate()


def test_valid_config_passes_validation():
    cfg = InstitutionalAccumulationConfig(
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        cnfb_bullish_windows=(20, 30),
        cnfb_bearish_windows=(3, 5, 7),
        foreign_vwap_days=20,
        domestic_vwap_days=20,
        broker_consistency_days=(10, 20),
        counterparty_window_days=5,
        min_sessions={},
        foreign_track_weights={"a": 0.5, "b": 0.5},
        domestic_track_weights={"x": 0.6, "y": 0.4},
        track_weights={"f": 0.45, "d": 0.4, "c": 0.15},
    )
    cfg.validate()  # should not raise


# --------------------------------------------------------------------------- #
# 9. Conviction renormalization (Finding 2 fix)
# --------------------------------------------------------------------------- #
def test_foreign_conviction_renormalized_when_components_missing():
    # Only foreign participation is available (all others absent).
    # Conviction should reflect participation score (0.8) renormalized to 1.0,
    # not participation * raw_weight (0.8 * 0.25 = 0.2).
    summaries = (_summary(0, fb=80.0, fs=0.0, total=100.0),)  # participation = 0.8
    result = _builder().build(_request(broker_summaries=summaries))
    track = result.foreign_institutional_track
    assert track.foreign_participation_score == pytest.approx(0.8, abs=1e-4)
    # Only one available slot with weight 0.25 → renormalized conviction = 0.8.
    assert track.conviction_score == pytest.approx(0.8, abs=1e-4)


def test_domestic_conviction_renormalized_when_some_components_missing():
    # Only bandar snapshot available (no flows) -> conviction reflects bandar score,
    # not bandar_weight * bandar_score (0.10 * x).
    result = _builder().build(_request(bandar_snapshot=_bandar("Big Acc")))
    track = result.domestic_bandar_track
    # broad_score with all "Big Acc" = 12 → normalized = 1.0
    assert track.bandar_broad_score_normalized == pytest.approx(1.0, abs=1e-4)
    # Only bandar slot available → conviction renormalizes to full weight → 1.0
    assert track.conviction_score == pytest.approx(1.0, abs=1e-4)


# --------------------------------------------------------------------------- #
# 10. CNFB metadata key structure (Finding 1 fix)
# --------------------------------------------------------------------------- #
def test_cnfb_bullish_scores_stored_per_window_in_metadata():
    # 20 sessions: verify both 20d and 30d sub-keys are stored in metadata.
    points = tuple(_ffp(off, 100.0) for off in range(30))
    candles = tuple(_candle(off, 500.0) for off in range(30))
    result = _builder().build(
        _request(foreign_flow_points=points, candles=candles)
    )
    bullish = result.metadata.get("cnfb_bullish_scores", {})
    assert "cnfb_20d" in bullish, "cnfb_20d raw score must be stored in metadata"
    assert "cnfb_30d" in bullish, "cnfb_30d raw score must be stored in metadata"


def test_cnfb_bearish_scores_stored_per_window_in_metadata():
    # 3+ sessions: verify cnfb_3d bearish score stored in cnfb_bearish_scores.
    # Bearish: positive cumulative CNFB slope (foreign selling) + rising price.
    points = tuple(_ffp(off, -50.0) for off in range(7))
    candles = tuple(_candle(off, 500.0 + off * 10) for off in range(7))
    result = _builder().build(
        _request(foreign_flow_points=points, candles=candles)
    )
    bearish = result.metadata.get("cnfb_bearish_scores", {})
    # At least cnfb_3d should be present if min sessions (2/3) are met.
    assert "cnfb_3d" in bearish, "cnfb_3d bearish score must be in cnfb_bearish_scores"


def test_ia_fingerprint_reads_raw_cnfb_window_keys():
    """_ia_evidence_fingerprint must read cnfb_bullish_scores/cnfb_bearish_scores."""
    from src.application.use_case.accumulation_screen_use_case import (
        _ia_evidence_fingerprint,
    )

    points = tuple(_ffp(off, 100.0) for off in range(30))
    candles = tuple(_candle(off, 500.0) for off in range(30))
    result = _builder().build(
        _request(foreign_flow_points=points, candles=candles)
    )
    fp = _ia_evidence_fingerprint(result)
    # Raw 20d score is in metadata["cnfb_bullish_scores"]["cnfb_20d"]
    expected_20d = result.metadata["cnfb_bullish_scores"]["cnfb_20d"]
    assert fp["ia_cnfb_divergence_20d"] == pytest.approx(expected_20d, abs=1e-6)
    expected_30d = result.metadata["cnfb_bullish_scores"]["cnfb_30d"]
    assert fp["ia_cnfb_divergence_30d"] == pytest.approx(expected_30d, abs=1e-6)


# --------------------------------------------------------------------------- #
# Broker classification config tests (Part 1)
# --------------------------------------------------------------------------- #

def test_config_loads_foreign_broker_codes_from_yaml():
    """YAML broker_classification.foreign_broker_codes is parsed into frozenset."""
    raw = {
        "institutional_accumulation": {
            "evidence_status": "DIAGNOSTIC",
            "broker_classification": {
                "foreign_broker_codes": ["zp", " YU ", "ak"]
            },
        }
    }
    config = InstitutionalAccumulationConfig.from_mapping(raw)
    assert "ZP" in config.foreign_broker_codes
    assert "YU" in config.foreign_broker_codes
    assert "AK" in config.foreign_broker_codes
    assert len(config.foreign_broker_codes) == 3


def test_local_flows_excludes_configured_foreign_codes():
    """Config-loaded foreign_broker_codes drive the local/foreign split."""
    config = InstitutionalAccumulationConfig.from_mapping({
        "institutional_accumulation": {
            "broker_classification": {
                "foreign_broker_codes": ["XX", "YY"],
            },
            "foreign_institutional_track_components": {
                "foreign_participation": 0.25,
                "foreign_concentration_cr4_cr8": 0.20,
                "cnfb_price_divergence": 0.35,
                "foreign_vwap_distance": 0.20,
            },
            "domestic_bandar_track_components": {
                "broker_consistency": 0.25,
                "broker_reversal": 0.15,
                "accumulation_session_ratio": 0.20,
                "domestic_buy_vwap_distance": 0.15,
                "broker_hhi_divergence": 0.15,
                "bandar_broad_or_accumulation_score": 0.10,
            },
            "track_weights": {
                "foreign_institutional_track": 0.45,
                "domestic_bandar_track": 0.40,
                "counterparty_transfer": 0.15,
            },
        }
    })
    builder = InstitutionalAccumulationEvidenceBuilder(config)

    flows = [
        _flow("XX", 0, buy=100.0, sell=0.0),
        _flow("YY", 0, buy=50.0, sell=0.0),
        _flow("PD", 0, buy=80.0, sell=0.0),
    ]

    assert [f.broker_code for f in builder._local_flows(flows)] == ["PD"]
    assert [f.broker_code for f in builder._foreign_flows(flows)] == ["XX", "YY"]


def test_fallback_when_yaml_omits_broker_classification():
    """Omitting broker_classification from YAML falls back to DEFAULT_FOREIGN_BROKER_CODES."""
    from src.application.services.institutional_accumulation_evidence_builder import (
        DEFAULT_FOREIGN_BROKER_CODES,
    )

    raw = {"institutional_accumulation": {"evidence_status": "DIAGNOSTIC"}}
    config = InstitutionalAccumulationConfig.from_mapping(raw)
    assert config.foreign_broker_codes == DEFAULT_FOREIGN_BROKER_CODES
