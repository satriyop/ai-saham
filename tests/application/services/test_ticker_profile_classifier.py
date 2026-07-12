"""Tests for TickerProfileClassifier (Phase F, diagnostic-only)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.application.dto.ticker_profile import TickerProfileConfig, TickerProfileRequest
from src.application.services.ticker_profile_classifier import (
    TickerProfileClassifier,
)
from src.domain.entities.broker_flow import BrokerDailyFlow, BrokerSummary
from src.domain.entities.candle import Candle
from src.domain.value_objects.institutional_accumulation_evidence import EvidenceStatus

BASE = date(2026, 6, 1)
LOCAL = "PD"
LOCAL2 = "CC"
LOCAL3 = "NI"
FOREIGN = "ZP"  # in DEFAULT_FOREIGN_BROKER_CODES


def _d(offset: int) -> date:
    return BASE + timedelta(days=offset)


def _config(**overrides) -> TickerProfileConfig:
    defaults = dict(
        evidence_status=EvidenceStatus.DIAGNOSTIC,
        profile_window_days=30,
        market_cap_large=10_000_000_000_000,
        market_cap_mid=1_000_000_000_000,
        market_cap_small=200_000_000_000,
        index_membership_scores={
            "lq45": 1.00,
            "idx30": 0.95,
            "idx80": 0.75,
            "jii": 0.65,
            "mbx": 0.50,
        },
        liquidity_high=50_000_000_000.0,
        liquidity_low=500_000_000.0,
        volatility_high=0.050,
        volatility_low=0.005,
        sparse_history_threshold=10,
        conservative_fallback_confidence=0.30,
        exposure_weights={
            "foreign_institutional": {
                "foreign_flow": 0.35,
                "index_membership": 0.30,
                "liquidity": 0.20,
                "broker_concentration_inverse": 0.15,
            },
            "domestic_bandar": {
                "broker_concentration": 0.45,
                "foreign_flow_inverse": 0.35,
                "liquidity": 0.20,
            },
            "retail_speculative": {
                "volatility": 0.40,
                "liquidity_inverse": 0.35,
                "market_cap_speculative": 0.25,
            },
        },
    )
    defaults.update(overrides)
    return TickerProfileConfig(**defaults)  # type: ignore[arg-type]


def _classifier(index=None, **config_overrides) -> TickerProfileClassifier:
    return TickerProfileClassifier(
        config=_config(**config_overrides),
        ticker_universe_index=index if index is not None else {},
    )


def _candle(offset: int, *, high: float, low: float, close: float, volume: int) -> Candle:
    return Candle(
        ticker="TEST",
        date=_d(offset),
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _flat_candles(
    n: int, *, high=100.0, low=99.0, close=100.0, volume=10_000
) -> tuple[Candle, ...]:
    return tuple(
        _candle(off, high=high, low=low, close=close, volume=volume)
        for off in range(n)
    )


def _flow(code: str, offset: int, *, buy: float) -> BrokerDailyFlow:
    return BrokerDailyFlow(
        ticker="TEST",
        broker_code=code,
        broker_name=code,
        date=_d(offset),
        buy_lot=int(buy),
        sell_lot=0,
        net_lot=int(buy),
        buy_value=Decimal(str(buy)),
        sell_value=Decimal("0"),
        net_value=Decimal(str(buy)),
        avg_buy_price=Decimal("100"),
        avg_sell_price=Decimal("100"),
        avg_price=Decimal("100"),
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


def _request(**overrides) -> TickerProfileRequest:
    defaults = dict(
        ticker="TEST",
        snapshot_date=_d(30),
        candles=(),
        broker_daily_flows=(),
        broker_summaries=(),
        market_cap_idr=None,
        sector=None,
        sub_sector=None,
    )
    defaults.update(overrides)
    return TickerProfileRequest(**defaults)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 1-2. Liquidity
# --------------------------------------------------------------------------- #
def test_liquidity_score_high_volume_candles():
    # high=1000, volume=100_000_000 -> daily_value=100B IDR >= 50B high -> ~1.0
    candles = tuple(
        _candle(off, high=1000.0, low=990.0, close=1000.0, volume=100_000_000)
        for off in range(12)
    )
    snap = _classifier().classify(_request(candles=candles))
    assert snap.liquidity_score == pytest.approx(1.0, abs=1e-4)


def test_liquidity_score_low_volume_candles():
    # high=100, volume=1000 -> daily_value=100k IDR <= 500M low -> 0.0
    candles = tuple(
        _candle(off, high=100.0, low=99.0, close=100.0, volume=1000)
        for off in range(12)
    )
    snap = _classifier().classify(_request(candles=candles))
    assert snap.liquidity_score == pytest.approx(0.0, abs=1e-4)


# --------------------------------------------------------------------------- #
# 3-4. Index membership
# --------------------------------------------------------------------------- #
def test_index_membership_score_lq45_ticker():
    clf = _classifier(index={"BBCA": ("lq45", "idx80")})
    snap = clf.classify(_request(ticker="BBCA", candles=_flat_candles(12)))
    assert snap.index_membership_score == pytest.approx(1.0, abs=1e-4)
    assert set(snap.index_memberships) == {"lq45", "idx80"}


def test_index_membership_score_not_in_any_index():
    clf = _classifier(index={"BBCA": ("lq45",)})
    snap = clf.classify(_request(ticker="GOTO", candles=_flat_candles(12)))
    assert snap.index_membership_score == 0.0
    assert snap.index_memberships == ()


# --------------------------------------------------------------------------- #
# 5-8. Market cap buckets
# --------------------------------------------------------------------------- #
def test_market_cap_bucket_large():
    snap = _classifier().classify(
        _request(
            candles=_flat_candles(12),
            market_cap_idr=Decimal("15_000_000_000_000".replace("_", "")),
        )
    )
    assert snap.market_cap_bucket == "large"


def test_market_cap_bucket_mid():
    snap = _classifier().classify(
        _request(candles=_flat_candles(12), market_cap_idr=Decimal("5000000000000"))
    )
    assert snap.market_cap_bucket == "mid"


def test_market_cap_bucket_small():
    snap = _classifier().classify(
        _request(candles=_flat_candles(12), market_cap_idr=Decimal("500000000000"))
    )
    assert snap.market_cap_bucket == "small"


def test_market_cap_bucket_micro():
    snap = _classifier().classify(
        _request(candles=_flat_candles(12), market_cap_idr=Decimal("100000000000"))
    )
    assert snap.market_cap_bucket == "micro"


def test_market_cap_bucket_unknown_when_unavailable():
    snap = _classifier().classify(
        _request(candles=_flat_candles(12), market_cap_idr=None)
    )
    assert snap.market_cap_bucket == "UNKNOWN"


def test_market_cap_bucket_unknown_when_malformed():
    snap = _classifier().classify(
        _request(candles=_flat_candles(12), market_cap_idr="not-a-number")
    )
    assert snap.market_cap_bucket == "UNKNOWN"


# --------------------------------------------------------------------------- #
# 9-12. Market tier (formerly profile_label — a market-cap/liquidity tier)
# --------------------------------------------------------------------------- #
def test_market_tier_blue_chip():
    clf = _classifier(index={"BBCA": ("lq45",)})
    snap = clf.classify(
        _request(
            ticker="BBCA",
            candles=_flat_candles(12),
            market_cap_idr=Decimal("15000000000000"),
        )
    )
    assert snap.market_tier == "blue_chip"


def test_market_tier_second_liner():
    clf = _classifier(index={"ANTM": ("idx80",)})
    snap = clf.classify(
        _request(
            ticker="ANTM",
            candles=_flat_candles(12),
            market_cap_idr=Decimal("5000000000000"),
        )
    )
    assert snap.market_tier == "second_liner"


def test_market_tier_third_liner():
    clf = _classifier(index={})
    snap = clf.classify(
        _request(
            ticker="GOTO",
            candles=_flat_candles(12),
            market_cap_idr=Decimal("100000000000"),
        )
    )
    assert snap.market_tier == "third_liner"


def test_market_tier_speculative():
    # Low liquidity (< 0.2) + high volatility (> 0.7), mid-ish cap so no cap bucket wins.
    # daily_value = 100 * 1000 = 100k -> ~0.0 liquidity.
    # True ATR: prev_close=100, high=150, low=50 -> TR=100, /100 = 1.0 -> saturates 1.0.
    candles = tuple(
        _candle(off, high=150.0, low=50.0, close=100.0, volume=1000)
        for off in range(12)
    )
    clf = _classifier(index={})
    # No market cap so bucket None; index 0.0. speculative must beat third_liner:
    # index==0.0 also triggers third_liner, but speculative is checked first.
    snap = clf.classify(_request(ticker="XXXX", candles=candles, market_cap_idr=None))
    assert snap.market_tier == "speculative"


# --------------------------------------------------------------------------- #
# 13. Sparse history
# --------------------------------------------------------------------------- #
def test_sparse_history_fallback():
    snap = _classifier().classify(_request(candles=_flat_candles(5)))
    assert snap.market_tier == "unknown"
    assert snap.primary_profile == "unclassified"
    assert snap.profile_confidence == pytest.approx(0.30, abs=1e-6)
    assert snap.foreign_institutional_exposure == pytest.approx(0.0, abs=1e-6)
    assert snap.domestic_bandar_exposure == pytest.approx(0.5, abs=1e-6)
    assert snap.retail_speculative_exposure == pytest.approx(0.5, abs=1e-6)


# --------------------------------------------------------------------------- #
# 14. Graceful degradation
# --------------------------------------------------------------------------- #
def test_graceful_degradation_never_raises():
    class Boom:
        broker_code = "PD"

        @property
        def date(self):  # noqa: A003 - mimic attribute used for windowing
            raise RuntimeError("boom")

    snap = _classifier().classify(
        _request(candles=_flat_candles(12), broker_daily_flows=(Boom(),))  # type: ignore[arg-type]
    )
    # Broker concentration degrades to None; classify still returns a snapshot.
    assert snap.broker_concentration_score is None
    assert snap.metadata["diagnostic_only"] is True
    assert snap.evidence_status is EvidenceStatus.DIAGNOSTIC


# --------------------------------------------------------------------------- #
# 15. Missing broker data reduces coverage
# --------------------------------------------------------------------------- #
def test_missing_broker_data_reduces_coverage():
    snap = _classifier().classify(
        _request(
            candles=_flat_candles(12),
            broker_daily_flows=(),
            broker_summaries=(),
        )
    )
    assert snap.broker_concentration_score is None
    assert snap.foreign_flow_score is None
    assert snap.coverage_score < 1.0


# --------------------------------------------------------------------------- #
# 16. Config validation
# --------------------------------------------------------------------------- #
def test_config_validation_rejects_invalid_index_score():
    cfg = _config(index_membership_scores={"lq45": 1.5})
    with pytest.raises(ValueError):
        cfg.validate()


def test_config_validation_rejects_invalid_exposure_weight_sum():
    cfg = _config(
        exposure_weights={
            "foreign_institutional": {
                "foreign_flow": 0.35,
                "index_membership": 0.30,
                "liquidity": 0.20,
                "broker_concentration_inverse": 0.30,
            }
        }
    )
    with pytest.raises(ValueError, match="must sum to 1.0"):
        cfg.validate()


def test_config_validation_rejects_negative_exposure_weight():
    cfg = _config(
        exposure_weights={
            "retail_speculative": {
                "volatility": 0.40,
                "liquidity_inverse": -0.10,
                "market_cap_speculative": 0.70,
            }
        }
    )
    with pytest.raises(ValueError, match="non-negative"):
        cfg.validate()


# --------------------------------------------------------------------------- #
# 17. Diagnostic-only metadata always set
# --------------------------------------------------------------------------- #
def test_diagnostic_only_metadata_always_set():
    snap = _classifier().classify(_request(candles=_flat_candles(12)))
    assert snap.metadata["diagnostic_only"] is True


def test_broker_concentration_hhi_local_only():
    # Two equal local brokers -> HHI = 0.5; foreign broker excluded.
    flows = (
        _flow(LOCAL, 0, buy=100.0),
        _flow(LOCAL2, 0, buy=100.0),
        _flow(FOREIGN, 0, buy=1000.0),  # excluded (foreign)
    )
    snap = _classifier().classify(
        _request(candles=_flat_candles(12), broker_daily_flows=flows)
    )
    assert snap.broker_concentration_score == pytest.approx(0.5, abs=1e-6)


def test_foreign_flow_score_from_summaries():
    # foreign (buy+sell) / total = (30+10)/100 = 0.4
    summaries = (_summary(0, fb=30.0, fs=10.0, total=100.0),)
    snap = _classifier().classify(
        _request(candles=_flat_candles(12), broker_summaries=summaries)
    )
    assert snap.foreign_flow_score == pytest.approx(0.4, abs=1e-6)


# --------------------------------------------------------------------------- #
# Phase F fixes: soft exposures, primary_profile, true ATR, margin confidence
# --------------------------------------------------------------------------- #
def _liquid_candles(n: int) -> tuple[Candle, ...]:
    # high=1000, volume=100M -> daily_value=100B >= 50B high -> liquidity ~1.0
    return tuple(
        _candle(off, high=1000.0, low=990.0, close=1000.0, volume=100_000_000)
        for off in range(n)
    )


def test_exposure_sums_to_one():
    snap = _classifier().classify(_request(candles=_flat_candles(12)))
    total = (
        snap.foreign_institutional_exposure
        + snap.domestic_bandar_exposure
        + snap.retail_speculative_exposure
    )
    assert total == pytest.approx(1.0, abs=1e-3)


def test_foreign_institutional_profile_high_foreign_flow():
    # High foreign flow + LQ45 membership + large cap -> foreign_institutional.
    summaries = tuple(
        _summary(off, fb=90.0, fs=0.0, total=100.0) for off in range(12)
    )
    clf = _classifier(index={"BBCA": ("lq45",)})
    snap = clf.classify(
        _request(
            ticker="BBCA",
            candles=_liquid_candles(12),
            broker_summaries=summaries,
            market_cap_idr=Decimal("15000000000000"),
        )
    )
    assert snap.primary_profile == "foreign_institutional"
    assert (
        snap.foreign_institutional_exposure > snap.domestic_bandar_exposure
        and snap.foreign_institutional_exposure > snap.retail_speculative_exposure
    )


def test_domestic_bandar_profile_high_concentration():
    # One dominant local broker (HHI ~1.0) + low foreign flow -> domestic_bandar.
    flows = tuple(_flow(LOCAL, off, buy=100.0) for off in range(12))
    summaries = tuple(
        _summary(off, fb=5.0, fs=0.0, total=100.0) for off in range(12)
    )
    snap = _classifier().classify(
        _request(
            ticker="BAND",
            candles=_flat_candles(12),
            broker_daily_flows=flows,
            broker_summaries=summaries,
        )
    )
    assert snap.primary_profile == "domestic_bandar"


def test_retail_speculative_profile_high_volatility_illiquid():
    # High volatility + illiquid + micro cap -> retail_speculative.
    candles = tuple(
        _candle(off, high=150.0, low=50.0, close=100.0, volume=1000)
        for off in range(12)
    )
    snap = _classifier().classify(
        _request(
            ticker="SPEC",
            candles=candles,
            market_cap_idr=Decimal("100000000000"),
        )
    )
    assert snap.primary_profile == "retail_speculative"


def test_profile_confidence_is_exposure_margin_not_coverage():
    # FI-heavy ticker: flows absent -> coverage 0.8, but confidence is the
    # exposure margin (primary minus second), which must differ from coverage.
    summaries = tuple(
        _summary(off, fb=90.0, fs=0.0, total=100.0) for off in range(12)
    )
    clf = _classifier(index={"BBCA": ("lq45",)})
    snap = clf.classify(
        _request(
            ticker="BBCA",
            candles=_liquid_candles(12),
            broker_summaries=summaries,
            market_cap_idr=Decimal("15000000000000"),
        )
    )
    ranked = sorted(
        (
            snap.foreign_institutional_exposure,
            snap.domestic_bandar_exposure,
            snap.retail_speculative_exposure,
        ),
        reverse=True,
    )
    expected_margin = round(ranked[0] - ranked[1], 4)
    assert snap.profile_confidence == pytest.approx(expected_margin, abs=1e-3)
    assert snap.profile_confidence != snap.coverage_score


def test_true_atr_uses_prev_close():
    # Day 2 gaps up: prev_close=100, high=155, low=148.
    # True Range = max(high-low=7, |high-prev_close|=55, |low-prev_close|=48) = 55.
    # Normalized by prev_close -> 0.55, distinct from range% (7/close).
    day1 = _candle(0, high=101.0, low=99.0, close=100.0, volume=10_000)
    day2 = _candle(1, high=155.0, low=148.0, close=150.0, volume=10_000)
    clf = _classifier(volatility_low=0.0, volatility_high=1.0)
    snap = clf.classify(_request(candles=(day1, day2)))
    assert snap.volatility_score == pytest.approx(0.55, abs=1e-3)


def test_market_tier_is_populated():
    snap = _classifier().classify(_request(candles=_flat_candles(12)))
    assert snap.market_tier in {
        "blue_chip",
        "second_liner",
        "third_liner",
        "speculative",
        "unknown",
    }


def test_primary_profile_in_snapshot():
    snap = _classifier().classify(_request(candles=_flat_candles(12)))
    assert snap.primary_profile is not None
    assert snap.primary_profile in {
        "foreign_institutional",
        "domestic_bandar",
        "retail_speculative",
    }
