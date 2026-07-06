from datetime import date

import pytest

from src.domain.value_objects.strategy_evidence import (
    StrategyEvidence,
    StrategyEvidenceOutcome,
    StrategyRuleEvidence,
)


def test_strategy_evidence_serializes_round_trip():
    evidence = StrategyEvidence(
        ticker="BBCA",
        snapshot_date=date(2026, 7, 1),
        strategy_name="Price Rule",
        outcome=StrategyEvidenceOutcome.MATCHED,
        matched_rule=StrategyRuleEvidence(
            strategy_name="Price Rule",
            rule_name="close_breakout",
            rule_outcome="LOW_RISK",
            evidence_route="strategy_yaml_supportive",
            setup_family="foreign-bounce",
            setup_phase="BREAKOUT_CONFIRMATION",
            rationale=("Custom rule 'close_breakout' matched",),
        ),
        coverage_score=1.0,
        conviction_score=1.0,
        freshness_score=1.0,
        rationale=("Custom rule 'close_breakout' matched",),
    )

    restored = StrategyEvidence.from_dict(evidence.to_dict())

    assert restored == evidence


def test_strategy_evidence_rejects_scores_outside_bounds():
    with pytest.raises(ValueError, match="coverage_score"):
        StrategyEvidence(
            ticker="BBCA",
            snapshot_date=date(2026, 7, 1),
            strategy_name="Price Rule",
            outcome=StrategyEvidenceOutcome.MATCHED,
            coverage_score=1.1,
        )
