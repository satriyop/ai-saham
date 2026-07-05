"""
Tests for RegimeDetectionEvidence value object and A2 helper functions.

Covers:
- Frozen dataclass immutability
- to_dict() completeness
- detection_inputs_dict() forward-label exclusion
- _compute_regime_confidence() edge cases
- _compute_ihsg_inputs() accuracy and trend structure
- _compute_foreign_flow_inputs() streaks and sums
- _compute_banking_vs_ihsg() guards and relative return
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.application.use_case.build_market_context_use_case import (
    _compute_banking_vs_ihsg,
    _compute_foreign_flow_inputs,
    _compute_ihsg_inputs,
    _compute_regime_confidence,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.market_context import MarketRegime
from src.domain.value_objects.regime_detection_evidence import (
    RegimeDetectionEvidence,
    RegimeStability,
)

# ── Shared thresholds ─────────────────────────────────────────────────────────

_THRESHOLDS = SimpleNamespace(
    risk_on_min_score=0.65,
    risk_off_max_score=0.40,
    volatile_vix_override=25.0,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_evidence(**kwargs) -> RegimeDetectionEvidence:
    defaults = dict(
        observation_date=date(2024, 1, 1),
        schema_version=1,
        regime="RISK_ON",
        regime_score=0.75,
        regime_confidence=0.8,
        regime_stability=RegimeStability.STABLE,
        days_in_regime=5,
        transition_warning=None,
        ihsg_20d_return=0.02,
        ihsg_trend_structure="ABOVE_BOTH",
        ihsg_breadth_pct_above_ma=65.0,
        ihsg_volume_trend=1.1,
        ihsg_atr_pct=0.8,
        idx_foreign_flow_5d=1_000_000_000.0,
        idx_foreign_flow_20d=5_000_000_000.0,
        foreign_buy_streak=3,
        foreign_sell_streak=0,
        banking_sector_vs_ihsg=0.5,
        sector_breadth=65.0,
    )
    defaults.update(kwargs)
    return RegimeDetectionEvidence(**defaults)


def _make_candles(
    ticker: str, prices: list[float], base_date: date = date(2024, 1, 1)
) -> list[Candle]:
    result = []
    for i, price in enumerate(prices):
        p = Decimal(str(price))
        d = base_date + timedelta(days=i)
        result.append(Candle(ticker=ticker, date=d, open=p, high=p, low=p, close=p, volume=1000))
    return result


def _make_flow_series(
    values: list[float], base_date: date = date(2024, 1, 1)
) -> list[tuple[date, Decimal]]:
    return [
        (base_date + timedelta(days=i), Decimal(str(v)))
        for i, v in enumerate(values)
    ]


# ── Value object tests ────────────────────────────────────────────────────────


def test_regime_detection_evidence_is_frozen():
    ev = _make_evidence()
    with pytest.raises((FrozenInstanceError, AttributeError)):
        ev.regime = "RISK_OFF"  # type: ignore[misc]


def test_to_dict_contains_all_keys():
    ev = _make_evidence()
    result = ev.to_dict()
    expected_keys = {
        "observation_date", "schema_version", "regime", "regime_score",
        "regime_confidence", "regime_stability", "days_in_regime", "transition_warning",
        "ihsg_20d_return", "ihsg_trend_structure", "ihsg_breadth_pct_above_ma",
        "ihsg_volume_trend", "ihsg_atr_pct", "idx_foreign_flow_5d", "idx_foreign_flow_20d",
        "foreign_buy_streak", "foreign_sell_streak", "banking_sector_vs_ihsg",
        "sector_breadth", "forward_ihsg_return_5d", "forward_ihsg_return_10d",
        "forward_ihsg_return_20d",
    }
    assert expected_keys.issubset(result.keys())


def test_detection_inputs_dict_excludes_forward_labels():
    ev = _make_evidence()
    result = ev.detection_inputs_dict()
    assert "forward_ihsg_return_5d" not in result
    assert "forward_ihsg_return_10d" not in result
    assert "forward_ihsg_return_20d" not in result


# ── Regime confidence tests ───────────────────────────────────────────────────


def test_regime_confidence_high_for_clear_risk_on():
    # conviction=0.85 → margin=0.20, boundary_half=0.125 → 1.6 → clamped 1.0
    confidence = _compute_regime_confidence(
        regime=MarketRegime.RISK_ON,
        conviction=0.85,
        vix_value=None,
        thresholds=_THRESHOLDS,
    )
    assert confidence == pytest.approx(1.0)


def test_regime_confidence_low_near_boundary():
    # conviction=0.66 (barely above min 0.65) → margin=0.01 / 0.125 ≈ 0.08
    confidence = _compute_regime_confidence(
        regime=MarketRegime.RISK_ON,
        conviction=0.66,
        vix_value=None,
        thresholds=_THRESHOLDS,
    )
    assert confidence <= 0.10


def test_regime_confidence_clamped_to_one():
    # conviction=0.99 far above boundary → clamped to 1.0
    confidence = _compute_regime_confidence(
        regime=MarketRegime.RISK_ON,
        conviction=0.99,
        vix_value=None,
        thresholds=_THRESHOLDS,
    )
    assert confidence == 1.0


# ── IHSG input tests ──────────────────────────────────────────────────────────


def test_ihsg_inputs_return_none_for_insufficient_candles():
    result = _compute_ihsg_inputs([])
    assert result["ihsg_20d_return"] is None
    assert result["ihsg_trend_structure"] is None
    assert result["ihsg_volume_trend"] is None
    assert result["ihsg_atr_pct"] is None


def test_ihsg_20d_return_computed_correctly():
    # 21 candles: first 20 at 5000, last at 5500 → (5500-5000)/5000*100 = 10.0%
    candles = _make_candles("IHSG", [5000] * 20 + [5500])
    result = _compute_ihsg_inputs(candles)
    assert result["ihsg_20d_return"] == pytest.approx(10.0, abs=0.001)


def test_ihsg_trend_structure_above_both():
    # 51 candles: 50 at 100, last at 200 → last close >> SMA20 (105) and SMA50 (102)
    candles = _make_candles("IHSG", [100] * 50 + [200])
    result = _compute_ihsg_inputs(candles)
    assert result["ihsg_trend_structure"] == "ABOVE_BOTH"


def test_ihsg_trend_structure_below_both():
    # 50 candles: 49 at 100, last at 50 → last close < SMA20 (97.5) and SMA50 (99)
    candles = _make_candles("IHSG", [100] * 49 + [50])
    result = _compute_ihsg_inputs(candles)
    assert result["ihsg_trend_structure"] == "BELOW_BOTH"


# ── Foreign flow tests ────────────────────────────────────────────────────────


def test_foreign_flow_buy_streak():
    series = _make_flow_series([-100.0, -50.0, 10.0, 20.0, 30.0])
    result = _compute_foreign_flow_inputs(series)
    assert result["foreign_buy_streak"] == 3
    assert result["foreign_sell_streak"] == 0


def test_foreign_flow_sell_streak():
    series = _make_flow_series([100.0, 50.0, -10.0, -20.0, -30.0, -40.0, -50.0])
    result = _compute_foreign_flow_inputs(series)
    assert result["foreign_sell_streak"] == 5
    assert result["foreign_buy_streak"] == 0


def test_foreign_flow_20d_sum():
    series = _make_flow_series([100.0] * 20)
    result = _compute_foreign_flow_inputs(series)
    assert result["idx_foreign_flow_20d"] == pytest.approx(2000.0, abs=0.01)


# ── Banking vs IHSG tests ─────────────────────────────────────────────────────


def test_banking_vs_ihsg_returns_none_when_no_universe():
    result = _compute_banking_vs_ihsg([], {}, [])
    assert result is None


def test_banking_vs_ihsg_returns_diff_of_returns():
    # IHSG: 5000 → 5250 = +5.0%; BBCA: 8000 → 8800 = +10%; BBRI: 4000 → 4600 = +15%
    # banking avg = 12.5%, diff = 12.5 - 5.0 = 7.5
    ihsg = _make_candles("IHSG", [5000] * 20 + [5250])
    bbca = _make_candles("BBCA", [8000] * 20 + [8800])
    bbri = _make_candles("BBRI", [4000] * 20 + [4600])
    result = _compute_banking_vs_ihsg(
        ["BBCA", "BBRI"],
        {"BBCA": bbca, "BBRI": bbri},
        ihsg,
    )
    assert result == pytest.approx(7.5, abs=0.001)
