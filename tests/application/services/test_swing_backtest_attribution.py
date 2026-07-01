from datetime import date
from decimal import Decimal
from math import inf

from src.application.services.swing_backtest_attribution import (
    DEFAULT_TUNING_TARGETS,
    AttributionBucketPolicy,
    build_tuning_proposal_draft,
    build_tuning_readiness_plan,
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
        "sample_quality": {
            "status": "INSUFFICIENT_SAMPLE",
            "completed_trade_count": 0,
            "candidate_observation_count": 0,
            "min_sample_size": 30,
            "trade_sample_ready": False,
            "candidate_sample_ready": False,
            "notes": [
                "No completed trades or candidate observations are available.",
                "Completed trades: 0/30 minimum.",
                "Candidate observations: 0/30 minimum.",
            ],
        },
        "group_stats": [],
        "candidate_group_stats": [],
        "tuning_targets": [
            target.to_dict() for target in DEFAULT_TUNING_TARGETS
        ],
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


def test_swing_backtest_attribution_tuning_targets_cover_current_dimensions():
    summary = summarize_swing_backtest_attribution(
        (_trade(ticker="BBCA", net_return_pct=5.0, pnl="500"),),
        (_Observation(forward_return_pct=4.0),),
    )

    emitted_dimensions = {
        stat.dimension
        for stat in (*summary.group_stats, *summary.candidate_group_stats)
    }
    target_by_dimension = {
        target.dimension: target
        for target in summary.tuning_targets
    }

    assert emitted_dimensions <= set(target_by_dimension)
    assert target_by_dimension["candidate_risk_status"].source_scope == "screened_candidates"
    assert target_by_dimension["risk_gate"].warning is not None
    assert "config/swing_setups.yaml:setups.*.gates" in (
        target_by_dimension["setup_gate"].yaml_paths
    )


def test_swing_backtest_attribution_marks_candidate_only_sample_quality():
    summary = summarize_swing_backtest_attribution(
        (),
        tuple(_Observation(forward_return_pct=1.0) for _ in range(30)),
    )

    quality = summary.sample_quality

    assert quality.status == "CANDIDATE_ONLY"
    assert quality.completed_trade_count == 0
    assert quality.candidate_observation_count == 30
    assert quality.trade_sample_ready is False
    assert quality.candidate_sample_ready is True
    assert "portfolio outcome tuning is blocked" in " ".join(quality.notes)


def test_swing_backtest_attribution_marks_trade_ready_sample_quality():
    summary = summarize_swing_backtest_attribution(
        tuple(
            _trade(ticker=f"BB{i:02d}", net_return_pct=1.0, pnl="100")
            for i in range(30)
        ),
        (),
    )

    quality = summary.sample_quality

    assert quality.status == "TRADE_READY"
    assert quality.completed_trade_count == 30
    assert quality.candidate_observation_count == 0
    assert quality.trade_sample_ready is True
    assert quality.candidate_sample_ready is False


def test_swing_backtest_attribution_marks_mixed_ready_sample_quality():
    summary = summarize_swing_backtest_attribution(
        tuple(
            _trade(ticker=f"BB{i:02d}", net_return_pct=1.0, pnl="100")
            for i in range(30)
        ),
        tuple(_Observation(forward_return_pct=1.0) for _ in range(30)),
    )

    quality = summary.sample_quality

    assert quality.status == "MIXED_READY"
    assert quality.trade_sample_ready is True
    assert quality.candidate_sample_ready is True


def test_tuning_readiness_plan_blocks_insufficient_sample():
    summary = summarize_swing_backtest_attribution(
        (_trade(ticker="BBCA", net_return_pct=5.0, pnl="500"),),
        (_Observation(forward_return_pct=1.0),),
    )

    plan = build_tuning_readiness_plan(summary)

    assert plan.intent == "readiness_gate_for_future_tuning_only"
    assert plan.status == "INSUFFICIENT_SAMPLE"
    assert plan.can_propose_changes is False
    assert plan.allowed_evidence_scopes == ()
    assert plan.allowed_config_families == ()
    assert plan.target_count == 0
    assert plan.blocked_reasons == summary.sample_quality.notes
    assert "No AI proposal" in " ".join(plan.notes)


def test_tuning_readiness_plan_allows_candidate_scoped_targets():
    summary = summarize_swing_backtest_attribution(
        (),
        tuple(_Observation(forward_return_pct=1.0) for _ in range(30)),
    )

    plan = build_tuning_readiness_plan(summary)

    assert plan.status == "CANDIDATE_ONLY"
    assert plan.can_propose_changes is True
    assert plan.allowed_evidence_scopes == ("screened_candidates",)
    assert plan.allowed_config_families == (
        "market_context",
        "risk",
        "setup",
        "signal",
        "signal_and_risk",
    )
    assert plan.target_count == 9
    assert plan.blocked_reasons == ()
    assert "portfolio outcome tuning is blocked" in " ".join(plan.notes)


def test_tuning_proposal_draft_blocks_insufficient_sample():
    summary = summarize_swing_backtest_attribution(
        (_trade(ticker="BBCA", net_return_pct=5.0, pnl="500"),),
        (_Observation(forward_return_pct=1.0),),
    )

    draft = build_tuning_proposal_draft(summary)

    assert draft.intent == "dry_run_tuning_proposal_contract_only"
    assert draft.status == "BLOCKED"
    assert draft.readiness_status == "INSUFFICIENT_SAMPLE"
    assert draft.can_generate_yaml_diff is False
    assert draft.requires_human_review is True
    assert draft.candidate_changes == ()
    assert len(draft.rejected_changes) == len(DEFAULT_TUNING_TARGETS)
    assert {
        rejection.reason
        for rejection in draft.rejected_changes
    } == {"Readiness gate blocks tuning proposals."}
    assert "No AI proposal" in " ".join(draft.evidence_notes)


def test_tuning_proposal_draft_lists_candidate_ready_review_targets():
    summary = summarize_swing_backtest_attribution(
        (),
        tuple(_Observation(forward_return_pct=1.0) for _ in range(30)),
    )

    draft = build_tuning_proposal_draft(summary)

    dimensions = {candidate.dimension for candidate in draft.candidate_changes}

    assert draft.status == "READY_FOR_HUMAN_REVIEW"
    assert draft.readiness_status == "CANDIDATE_ONLY"
    assert draft.can_generate_yaml_diff is False
    assert draft.requires_human_review is True
    assert dimensions == {
        "candidate_setup_match",
        "candidate_signal_strength",
        "candidate_signal_score_bucket",
        "candidate_signal_factor_bucket",
        "candidate_trade_setup_action",
        "setup_gate",
    }
    assert all(candidate.evidence_buckets for candidate in draft.candidate_changes)
    assert {
        rejection.dimension
        for rejection in draft.rejected_changes
        if rejection.reason == "No attribution buckets are available for this dimension."
    } == {"candidate_risk_gate", "candidate_risk_status", "candidate_regime"}


def test_swing_backtest_attribution_summary_golden_contract():
    summary = summarize_swing_backtest_attribution(
        (
            _trade(
                ticker="BBCA",
                net_return_pct=5.0,
                pnl="500",
                signal_score=72,
            ),
        ),
        (
            _Observation(
                forward_return_pct=-2.0,
                setup_match="NO_MATCH",
                signal_score=40,
            ),
        ),
    )

    payload = summary.to_dict()

    assert payload["intent"] == "learning_summary_only_not_entry_logic"
    assert payload["bucket_policy"] == {
        "high_min_score": 70.0,
        "mid_min_score": 45.0,
    }
    assert payload["sample_quality"] == {
        "status": "INSUFFICIENT_SAMPLE",
        "completed_trade_count": 1,
        "candidate_observation_count": 1,
        "min_sample_size": 30,
        "trade_sample_ready": False,
        "candidate_sample_ready": False,
        "notes": [
            "Samples are below the minimum required for tuning suggestions.",
            "Completed trades: 1/30 minimum.",
            "Candidate observations: 1/30 minimum.",
        ],
    }
    assert payload["group_stats"] == [
        {
            "dimension": "regime",
            "bucket": "RISK_ON",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
        {
            "dimension": "risk_status",
            "bucket": "OPEN",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
        {
            "dimension": "setup_gate",
            "bucket": "foreign_flow_score:PASS",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
        {
            "dimension": "setup_gate",
            "bucket": "vwap_discount:PASS",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
        {
            "dimension": "signal_factor_bucket",
            "bucket": "bandar_intensity:HIGH_70_PLUS",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
        {
            "dimension": "signal_factor_bucket",
            "bucket": "foreign_flow_quality:HIGH_70_PLUS",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
        {
            "dimension": "signal_score_bucket",
            "bucket": "HIGH_70_PLUS",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
        {
            "dimension": "signal_strength",
            "bucket": "STRONG",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
        {
            "dimension": "trade_setup_action",
            "bucket": "ENTER",
            "trade_count": 1,
            "win_rate_pct": 100.0,
            "avg_return_pct": 5.0,
            "total_pnl": "500",
            "profit_factor": inf,
        },
    ]
    assert payload["candidate_group_stats"] == [
        {
            "dimension": "candidate_setup_match",
            "bucket": "NO_MATCH",
            "observation_count": 1,
            "win_rate_pct": 0.0,
            "avg_forward_return_pct": -2.0,
        },
        {
            "dimension": "candidate_signal_factor_bucket",
            "bucket": "foreign_flow_quality:LOW_BELOW_45",
            "observation_count": 1,
            "win_rate_pct": 0.0,
            "avg_forward_return_pct": -2.0,
        },
        {
            "dimension": "candidate_signal_score_bucket",
            "bucket": "LOW_BELOW_45",
            "observation_count": 1,
            "win_rate_pct": 0.0,
            "avg_forward_return_pct": -2.0,
        },
        {
            "dimension": "candidate_signal_strength",
            "bucket": "WEAK",
            "observation_count": 1,
            "win_rate_pct": 0.0,
            "avg_forward_return_pct": -2.0,
        },
        {
            "dimension": "candidate_trade_setup_action",
            "bucket": "WATCH",
            "observation_count": 1,
            "win_rate_pct": 0.0,
            "avg_forward_return_pct": -2.0,
        },
        {
            "dimension": "setup_gate",
            "bucket": "vwap_discount:FAIL",
            "observation_count": 1,
            "win_rate_pct": 0.0,
            "avg_forward_return_pct": -2.0,
        },
    ]
    assert payload["tuning_targets"] == [
        target.to_dict() for target in DEFAULT_TUNING_TARGETS
    ]
