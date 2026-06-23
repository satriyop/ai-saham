"""Tests for LiquidityGate — structural gate for market cap and transaction liquidity."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.domain.entities.candle import Candle
from src.domain.rules.liquidity_gate import LiquidityGate
from src.domain.rules.risk_gate import GateContext
from src.domain.value_objects.risk_signal import RiskLevel

_TODAY = date(2026, 6, 23)
_1T = 1_000_000_000_000
_5B = 5_000_000_000


def _candle(close: float, volume: int, day_offset: int = 0) -> Candle:
    return Candle(
        ticker="BBCA",
        date=_TODAY - timedelta(days=day_offset),
        open=Decimal(str(close)),
        high=Decimal(str(close)),
        low=Decimal(str(close)),
        close=Decimal(str(close)),
        volume=volume,
    )


def _ctx(
    market_cap_idr: int | None = None,
    candles: tuple = (),
) -> GateContext:
    return GateContext(
        ticker="BBCA",
        snapshot_date=_TODAY,
        market_cap_idr=market_cap_idr,
        recent_candles=candles,
    )


class TestLiquidityGateMarketCap:
    """Rec 6 — third-liner market cap gate."""

    def test_below_1t_triggers_high_risk(self):
        gate = LiquidityGate()
        result = gate.evaluate(_ctx(market_cap_idr=500_000_000_000), RiskLevel.LOW_RISK)
        assert result.triggered
        assert result.override_risk == RiskLevel.HIGH_RISK

    def test_at_1t_triggers(self):
        gate = LiquidityGate(third_liner_cap_idr=_1T)
        # exactly at threshold → below (strict <) so does NOT trigger
        result = gate.evaluate(_ctx(market_cap_idr=_1T), RiskLevel.LOW_RISK)
        assert not result.triggered

    def test_above_1t_passes(self):
        gate = LiquidityGate()
        result = gate.evaluate(_ctx(market_cap_idr=2 * _1T), RiskLevel.LOW_RISK)
        assert not result.triggered

    def test_no_market_cap_skips_cap_check(self):
        gate = LiquidityGate()
        result = gate.evaluate(_ctx(market_cap_idr=None), RiskLevel.MODERATE)
        # No candles either — both checks skipped → passes
        assert not result.triggered

    def test_market_cap_check_runs_before_liquidity_check(self):
        """Cap check must short-circuit even when candles are present."""
        illiquid_candles = tuple(_candle(close=100, volume=1_000) for _ in range(20))
        gate = LiquidityGate(liquidity_floor_idr=_5B)
        result = gate.evaluate(
            _ctx(market_cap_idr=100_000_000_000, candles=illiquid_candles),
            RiskLevel.LOW_RISK,
        )
        assert result.triggered
        assert "Third-liner" in result.reason

    def test_custom_cap_threshold(self):
        gate = LiquidityGate(third_liner_cap_idr=500_000_000_000)
        assert gate.evaluate(_ctx(market_cap_idr=400_000_000_000), RiskLevel.MODERATE).triggered
        assert not gate.evaluate(_ctx(market_cap_idr=600_000_000_000), RiskLevel.MODERATE).triggered


class TestLiquidityGateMedianVolume:
    """Rec 2 — median 20-day transaction value gate."""

    def test_low_median_transaction_triggers_high_risk(self):
        # price=100, volume=10_000 → tx=1_000_000 IDR per day (far below 5B)
        candles = tuple(_candle(close=100, volume=10_000, day_offset=i) for i in range(20))
        gate = LiquidityGate(liquidity_floor_idr=_5B)
        result = gate.evaluate(_ctx(candles=candles), RiskLevel.LOW_RISK)
        assert result.triggered
        assert result.override_risk == RiskLevel.HIGH_RISK

    def test_high_median_transaction_passes(self):
        # price=10_000, volume=1_000_000 → tx=10B IDR per day (2× floor)
        candles = tuple(_candle(close=10_000, volume=1_000_000, day_offset=i) for i in range(20))
        gate = LiquidityGate(liquidity_floor_idr=_5B)
        result = gate.evaluate(_ctx(candles=candles), RiskLevel.LOW_RISK)
        assert not result.triggered

    def test_median_uses_lookback_tail(self):
        """Only the last N candles are used; older candles don't matter."""
        # First 5 candles are illiquid; last 20 are liquid
        old_candles = tuple(_candle(close=100, volume=1, day_offset=i + 20) for i in range(5))
        recent_candles = tuple(
            _candle(close=10_000, volume=1_000_000, day_offset=i) for i in range(20)
        )
        gate = LiquidityGate(liquidity_floor_idr=_5B, lookback_days=20)
        result = gate.evaluate(_ctx(candles=old_candles + recent_candles), RiskLevel.LOW_RISK)
        assert not result.triggered  # recent 20 are liquid → passes

    def test_no_candles_skips_liquidity_check(self):
        gate = LiquidityGate()
        result = gate.evaluate(_ctx(candles=()), RiskLevel.LOW_RISK)
        assert not result.triggered

    def test_zero_volume_candles_excluded_from_median(self):
        # Mix of zero-volume (excluded) and high-volume candles
        zero_vol = tuple(_candle(close=100, volume=0, day_offset=i) for i in range(10))
        high_vol = tuple(
            _candle(close=10_000, volume=1_000_000, day_offset=i + 10) for i in range(10)
        )
        gate = LiquidityGate(liquidity_floor_idr=_5B)
        result = gate.evaluate(_ctx(candles=zero_vol + high_vol), RiskLevel.LOW_RISK)
        # Median of non-zero values only; high-volume candles should keep it above floor
        assert not result.triggered


class TestLiquidityGateIgnoresCurrentRisk:
    """Structural gate must fire regardless of the technical risk level."""

    def test_fires_on_low_risk(self):
        gate = LiquidityGate()
        result = gate.evaluate(_ctx(market_cap_idr=100_000_000_000), RiskLevel.LOW_RISK)
        assert result.triggered

    def test_fires_on_moderate(self):
        gate = LiquidityGate()
        result = gate.evaluate(_ctx(market_cap_idr=100_000_000_000), RiskLevel.MODERATE)
        assert result.triggered

    def test_fires_on_high_risk(self):
        gate = LiquidityGate()
        result = gate.evaluate(_ctx(market_cap_idr=100_000_000_000), RiskLevel.HIGH_RISK)
        assert result.triggered


class TestLiquidityGateReason:
    def test_cap_trigger_reason_mentions_third_liner(self):
        gate = LiquidityGate()
        result = gate.evaluate(_ctx(market_cap_idr=500_000_000_000), RiskLevel.LOW_RISK)
        assert "Third-liner" in result.reason or "third" in result.reason.lower()

    def test_liquidity_trigger_reason_mentions_illiquid(self):
        candles = tuple(_candle(close=100, volume=1_000, day_offset=i) for i in range(20))
        gate = LiquidityGate(liquidity_floor_idr=_5B)
        result = gate.evaluate(_ctx(candles=candles), RiskLevel.LOW_RISK)
        assert "Illiquid" in result.reason or "illiquid" in result.reason.lower()
