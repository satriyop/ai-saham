"""ADR-054 S1: AccumulationCandidate.to_dict always exposes trade_setup."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from src.application.dto.accumulation_screen import AccumulationCandidate
from src.domain.value_objects.signal_assessment import SignalStrength
from src.domain.value_objects.trade_setup import SetupAction, TradeSetup


def _minimal_candidate(**kwargs) -> AccumulationCandidate:
    base = dict(
        ticker="BBCA",
        window_days=7,
        net_buy_days=5,
        total_days=7,
        net_buy_ratio=0.7,
        total_net_value=Decimal("1000"),
        consecutive_streak=3,
        foreign_vwap=Decimal("100"),
        current_price=Decimal("100"),
        vwap_discount_pct=1.0,
        rsi=50.0,
        trend="SIDE",
        accum_score=60.0,
        top_brokers=[],
        institutional_flag=False,
    )
    base.update(kwargs)
    return AccumulationCandidate(**base)


def test_to_dict_trade_setup_null_when_absent() -> None:
    d = _minimal_candidate().to_dict()
    assert "trade_setup" in d
    assert d["trade_setup"] is None


def test_to_dict_trade_setup_serializes_action() -> None:
    setup = TradeSetup(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 28),
        action=SetupAction.ENTER,
        signal_score=80,
        signal_score_raw=80,
        signal_strength=SignalStrength.STRONG,
        blocking_gates=(),
        regime=None,
        signal_multiplier=1.0,
        gate_tightening=False,
        rationale="open",
    )
    d = _minimal_candidate(trade_setup=setup).to_dict()
    assert d["trade_setup"] is not None
    assert d["trade_setup"]["action"] == "ENTER"
    assert d["trade_setup"]["ticker"] == "BBCA"
    assert d["trade_setup"]["signal_score"] == 80
