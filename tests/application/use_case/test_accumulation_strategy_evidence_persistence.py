from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from src.application.use_case.accumulation_screen_use_case import (
    AccumulationScreenRequest,
    _candidate_observation_payload,
)
from src.domain.value_objects.strategy_evidence import (
    StrategyEvidence,
    StrategyEvidenceOutcome,
    StrategyRuleEvidence,
)


def test_candidate_observation_payload_persists_strategy_evidence_fields():
    strategy_evidence = StrategyEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        strategy_name="Price Breakout",
        outcome=StrategyEvidenceOutcome.MATCHED,
        matched_rule=StrategyRuleEvidence(
            strategy_name="Price Breakout",
            rule_name="close_breakout",
            rule_outcome="LOW_RISK",
            evidence_route="strategy_yaml_supportive",
            setup_family="accumulation",
            setup_phase="BREAKOUT_CONFIRMATION",
        ),
        coverage_score=1.0,
        conviction_score=1.0,
        freshness_score=1.0,
        rationale=("Custom rule 'close_breakout' matched",),
    )

    payload = _candidate_observation_payload(
        _candidate(),
        screen_result="pass",
        flow_ev=None,
        setup_phase=None,
        strategy_evidence=strategy_evidence,
        snapshot_date=date(2026, 7, 1),
        captured_at=datetime(2026, 7, 1, 9, 0, 0),
        request=AccumulationScreenRequest(
            tickers=["BBCA"],
            strategy_name="price-breakout",
        ),
    )

    fp = payload["sub_signal_fingerprint"]
    assert fp["strategy_name"] == "Price Breakout"
    assert fp["strategy_rule_name"] == "close_breakout"
    assert fp["strategy_rule_outcome"] == "LOW_RISK"
    assert fp["strategy_evidence_outcome"] == "MATCHED"
    assert fp["strategy_evidence_route"] == "strategy_yaml_supportive"
    assert fp["strategy_coverage_score"] == 1.0
    assert fp["strategy_conviction_score"] == 1.0
    assert fp["strategy_freshness_score"] == 1.0


def _candidate():
    return SimpleNamespace(
        ticker="BBCA",
        signal_assessment=None,
        rsi=55.0,
        bb_width_pctile=0.2,
        vwap_pct=1.5,
        avg_flow_ratio=2.0,
        total_net_value=Decimal("1000000000"),
        net_buy_ratio=0.7,
        bandar_detector=None,
        to_dict=lambda: {"ticker": "BBCA"},
        trade_setup=None,
    )
