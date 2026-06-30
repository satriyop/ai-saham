from datetime import date
from decimal import Decimal

from src.application.services.swing_backtest_attribution import (
    AttributionBucketPolicy,
    summarize_swing_backtest_attribution,
)
from src.application.use_case.swing_backtest_use_case import SwingBacktestTrade
from src.domain.value_objects.setup_evaluation import SetupGate


class _Observation:
    def __init__(
        self,
        *,
        forward_return_pct: float,
        setup_match: str = "NO_MATCH",
        signal_score: int = 40,
        risk_status: str | None = None,
    ) -> None:
        self.forward_return_pct = forward_return_pct
        self.setup_match = setup_match
        self.signal_score = signal_score
        self.signal_strength = "WEAK"
        self.signal_breakdown = (("foreign_flow_quality", float(signal_score)),)
        self.setup_gates = (
            SetupGate("vwap_discount", False, "1", ">= 3"),
        )
        self.risk_status = risk_status
        self.risk_gate = None
        self.trade_setup_action = "WATCH"
        self.regime = None


def _trade(
    *,
    ticker: str,
    net_return_pct: float,
    pnl: str,
    signal_strength: str | None = "STRONG",
    signal_score: int | None = 72,
    risk_status: str | None = "OPEN",
    risk_gate: str | None = None,
    regime: str | None = "RISK_ON",
) -> SwingBacktestTrade:
    return SwingBacktestTrade(
        ticker=ticker,
        entry_date=date(2026, 1, 1),
        exit_date=date(2026, 1, 2),
        entry_price=Decimal("100"),
        exit_price=Decimal("105"),
        lots=1,
        shares=100,
        entry_value=Decimal("10000"),
        exit_value=Decimal("10500"),
        gross_return_pct=5.0,
        net_return_pct=net_return_pct,
        pnl=Decimal(pnl),
        holding_days=1,
        exit_reason="target" if net_return_pct > 0 else "stop",
        foreign_flow_score=80.0,
        flow_pct=10.0,
        vwap_disc_pct=5.0,
        rsi=50.0,
        regime=regime,
        setup_match="MATCH",
        setup_gates=(
            SetupGate("foreign_flow_score", True, "80", ">= 70"),
            SetupGate("vwap_discount", net_return_pct > 0, "5", ">= 3"),
        ),
        trade_setup_action="ENTER",
        signal_score=signal_score,
        signal_strength=signal_strength,
        signal_entry_quality="ENTER",
        signal_breakdown=(
            ("bandar_intensity", 75.0),
            ("foreign_flow_quality", 82.0),
        ),
        risk_status=risk_status,
        risk_gate=risk_gate,
    )


def test_summarize_swing_backtest_attribution_groups_tuning_dimensions():
    summary = summarize_swing_backtest_attribution((
        _trade(ticker="BBCA", net_return_pct=5.0, pnl="500"),
        _trade(
            ticker="BBRI",
            net_return_pct=-3.0,
            pnl="-300",
            signal_strength="MODERATE",
            signal_score=55,
            risk_status="BLOCKED",
            risk_gate="LiquidityGate",
            regime="RISK_OFF",
        ),
    ))

    by_key = {
        (stat.dimension, stat.bucket): stat
        for stat in summary.group_stats
    }

    assert summary.intent == "learning_summary_only_not_entry_logic"
    assert by_key[("signal_strength", "STRONG")].trade_count == 1
    assert by_key[("signal_score_bucket", "MID_45_69")].trade_count == 1
    assert by_key[("risk_status", "BLOCKED")].avg_return_pct == -3.0
    assert by_key[("risk_gate", "LiquidityGate")].win_rate_pct == 0.0
    assert by_key[("setup_gate", "vwap_discount:FAIL")].trade_count == 1
    assert by_key[("signal_factor_bucket", "foreign_flow_quality:HIGH_70_PLUS")].trade_count == 2
    assert by_key[("trade_setup_action", "ENTER")].total_pnl == Decimal("200")


def test_empty_swing_backtest_attribution_summary_is_deterministic():
    summary = summarize_swing_backtest_attribution(())

    assert summary.group_stats == ()
    assert summary.to_dict() == {
        "intent": "learning_summary_only_not_entry_logic",
        "bucket_policy": {
            "high_min_score": 70.0,
            "mid_min_score": 45.0,
        },
        "group_stats": [],
        "candidate_group_stats": [],
    }


def test_summarize_swing_backtest_attribution_uses_configured_score_buckets():
    summary = summarize_swing_backtest_attribution(
        (_trade(ticker="BBCA", net_return_pct=5.0, pnl="500", signal_score=65),),
        bucket_policy=AttributionBucketPolicy(high_min_score=80.0, mid_min_score=60.0),
    )

    by_key = {
        (stat.dimension, stat.bucket): stat
        for stat in summary.group_stats
    }

    assert by_key[("signal_score_bucket", "MID_60_79")].trade_count == 1
    assert by_key[("signal_factor_bucket", "bandar_intensity:MID_60_79")].trade_count == 1
    assert by_key[("signal_factor_bucket", "foreign_flow_quality:HIGH_80_PLUS")].trade_count == 1


def test_summarize_swing_backtest_attribution_groups_candidate_observations():
    summary = summarize_swing_backtest_attribution(
        (),
        (
            _Observation(forward_return_pct=4.0, setup_match="NO_MATCH", signal_score=40),
            _Observation(forward_return_pct=-2.0, setup_match="MATCH", signal_score=75),
        ),
    )

    by_key = {
        (stat.dimension, stat.bucket): stat
        for stat in summary.candidate_group_stats
    }

    assert by_key[("candidate_setup_match", "NO_MATCH")].avg_forward_return_pct == 4.0
    assert by_key[("candidate_setup_match", "MATCH")].win_rate_pct == 0.0
    assert by_key[("setup_gate", "vwap_discount:FAIL")].observation_count == 2
    assert by_key[("candidate_signal_score_bucket", "LOW_BELOW_45")].observation_count == 1
