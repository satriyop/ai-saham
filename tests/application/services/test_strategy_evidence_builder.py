from datetime import date, timedelta
from decimal import Decimal

from src.application.services.strategy_evidence_builder import (
    StrategyEvidenceBuilder,
    StrategyEvidenceRequest,
)
from src.domain.entities.candle import Candle
from src.domain.value_objects.strategy_evidence import StrategyEvidenceOutcome
from src.infrastructure.config.rules_yaml_loader import RulesYamlLoader


def test_strategy_evidence_builder_matches_price_rule(tmp_path):
    strategy_path = tmp_path / "strategy.yaml"
    strategy_path.write_text(
        """
version: 1
name: "Price Breakout"
default_outcome: MODERATE
rules:
  - name: close_breakout
    when:
      left:
        indicator: CLOSE
      operator: ">"
      right:
        value: 1000
    outcome: LOW_RISK
    rationale: "Close is above breakout threshold"
""",
        encoding="utf-8",
    )

    evidence = StrategyEvidenceBuilder(rules_loader=RulesYamlLoader()).build(
        StrategyEvidenceRequest(
            ticker="BBCA",
            strategy_name=strategy_path,
            candles=tuple(_candles(close=Decimal("1050"))),
            snapshot_date=date(2026, 7, 1),
            setup_family="foreign-bounce",
            setup_phase="BREAKOUT_CONFIRMATION",
        )
    )

    assert evidence.outcome == StrategyEvidenceOutcome.MATCHED
    assert evidence.strategy_name == "Price Breakout"
    assert evidence.matched_rule is not None
    assert evidence.matched_rule.rule_name == "close_breakout"
    assert evidence.matched_rule.rule_outcome == "LOW_RISK"
    assert evidence.matched_rule.evidence_route == "strategy_yaml_supportive"
    assert evidence.coverage_score == 1.0
    assert evidence.conviction_score == 1.0


def test_strategy_evidence_builder_returns_unavailable_for_empty_candles(tmp_path):
    strategy_path = tmp_path / "strategy.yaml"
    strategy_path.write_text(
        """
version: 1
name: "Price Breakout"
default_outcome: MODERATE
rules:
  - name: close_breakout
    when:
      left:
        indicator: CLOSE
      operator: ">"
      right:
        value: 1000
    outcome: LOW_RISK
""",
        encoding="utf-8",
    )

    evidence = StrategyEvidenceBuilder(rules_loader=RulesYamlLoader()).build(
        StrategyEvidenceRequest(
            ticker="BBCA",
            strategy_name=strategy_path,
            candles=(),
            snapshot_date=date(2026, 7, 1),
        )
    )

    assert evidence.outcome == StrategyEvidenceOutcome.UNAVAILABLE
    assert evidence.unavailable_reasons == ("no_candles",)


def test_strategy_evidence_builder_reports_not_matched_when_default_used(tmp_path):
    strategy_path = tmp_path / "strategy.yaml"
    strategy_path.write_text(
        """
version: 1
name: "Price Breakout"
default_outcome: MODERATE
rules:
  - name: close_breakout
    when:
      left:
        indicator: CLOSE
      operator: ">"
      right:
        value: 1000
    outcome: LOW_RISK
""",
        encoding="utf-8",
    )

    evidence = StrategyEvidenceBuilder(rules_loader=RulesYamlLoader()).build(
        StrategyEvidenceRequest(
            ticker="BBCA",
            strategy_name=strategy_path,
            candles=tuple(_candles(close=Decimal("950"))),
            snapshot_date=date(2026, 7, 1),
        )
    )

    assert evidence.outcome == StrategyEvidenceOutcome.NOT_MATCHED
    assert evidence.matched_rule.rule_name is None
    assert evidence.matched_rule.rule_outcome == "MODERATE"
    assert evidence.conviction_score == 0.0


def test_strategy_evidence_builder_reports_invalid_strategy(tmp_path):
    strategy_path = tmp_path / "strategy.yaml"
    strategy_path.write_text("not: a strategy", encoding="utf-8")

    evidence = StrategyEvidenceBuilder(rules_loader=RulesYamlLoader()).build(
        StrategyEvidenceRequest(
            ticker="BBCA",
            strategy_name=strategy_path,
            candles=tuple(_candles(close=Decimal("1050"))),
            snapshot_date=date(2026, 7, 1),
        )
    )

    assert evidence.outcome == StrategyEvidenceOutcome.INVALID
    assert evidence.unavailable_reasons


def _candles(close: Decimal) -> list[Candle]:
    start = date(2026, 6, 27)
    return [
        Candle(
            ticker="BBCA",
            date=start + timedelta(days=idx),
            open=Decimal("990"),
            high=Decimal("1060"),
            low=Decimal("980"),
            close=close,
            volume=1_000_000,
        )
        for idx in range(5)
    ]
