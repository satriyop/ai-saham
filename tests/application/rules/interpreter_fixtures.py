from datetime import date
from decimal import Decimal

from src.application.rules.schema import (
    ConditionIndicatorVsIndicator,
    ConditionIndicatorVsValue,
    IndicatorRef,
    Operator,
    Outcome,
    Rule,
    RuleSet,
)
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot


def make_snapshot(
    rsi: str = "50",
    sma: str = "100",
    ema: str = "100",
    extras: tuple[tuple[str, Decimal], ...] = (),
) -> IndicatorSnapshot:
    """Create a test indicator snapshot."""
    return IndicatorSnapshot(
        date=date.today(),
        rsi=Decimal(rsi),
        sma=Decimal(sma),
        ema=Decimal(ema),
        extras=extras,
    )


def make_rule(
    name: str,
    indicator_name: str = "RSI",
    operator: Operator = Operator.LT,
    value: str = "30",
    outcome: Outcome = Outcome.LOW_RISK,
    priority: int = 100,
    rationale: str | None = None,
) -> Rule:
    """Create a test rule with indicator vs value condition."""
    return Rule(
        name=name,
        condition=ConditionIndicatorVsValue(
            indicator_name=indicator_name,
            operator=operator,
            value=Decimal(value),
        ),
        outcome=outcome,
        priority=priority,
        rationale=rationale,
    )


def make_indicator_rule(
    name: str,
    left: str = "EMA",
    operator: Operator = Operator.GT,
    right: str = "SMA",
    outcome: Outcome = Outcome.LOW_RISK,
    priority: int = 100,
) -> Rule:
    """Create a test rule with indicator vs indicator condition."""
    return Rule(
        name=name,
        condition=ConditionIndicatorVsIndicator(
            left=IndicatorRef(name=left),
            operator=operator,
            right=IndicatorRef(name=right),
        ),
        outcome=outcome,
        priority=priority,
    )


def make_rule_set(
    rules: list[Rule],
    default_outcome: Outcome = Outcome.MODERATE,
    name: str = "test_rules",
) -> RuleSet:
    """Create a test rule set."""
    return RuleSet(
        version=1,
        name=name,
        default_outcome=default_outcome,
        rules=tuple(rules),
    )
