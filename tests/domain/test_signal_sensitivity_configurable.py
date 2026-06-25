"""Tests for YAML-configurable signal sensitivity thresholds."""

from datetime import date
from decimal import Decimal

from src.application.services.bootstrap import _resolve_rule_sets
from src.domain.rules.aggressive import AggressiveRuleSet
from src.domain.rules.balanced import BalancedRuleSet
from src.domain.rules.conservative import ConservativeRuleSet
from src.domain.rules.rule_engine import RuleEngine
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_signal import RiskLevel, SignalSensitivity


def _snap(rsi: str, ema: str = "99", sma: str = "100") -> IndicatorSnapshot:
    return IndicatorSnapshot(
        date=date(2026, 1, 1),
        sma=Decimal(sma),
        ema=Decimal(ema),
        rsi=Decimal(rsi),
    )


def test_conservative_accepts_custom_thresholds():
    rs = ConservativeRuleSet(rsi_high_risk=Decimal("80"), rsi_low_risk=Decimal("20"))
    assert rs.RSI_HIGH_RISK == Decimal("80")
    assert rs.RSI_LOW_RISK == Decimal("20")
    # RSI 77 is below the custom threshold of 80 — should NOT fire high-risk alone
    level, _, _ = rs.evaluate(_snap("77"))
    assert level != RiskLevel.HIGH_RISK


def test_rule_engine_accepts_custom_rule_sets():
    engine = RuleEngine(rule_sets={
        SignalSensitivity.CONSERVATIVE: ConservativeRuleSet(rsi_high_risk=Decimal("80")),
        SignalSensitivity.BALANCED: BalancedRuleSet(),
        SignalSensitivity.AGGRESSIVE: AggressiveRuleSet(),
    })
    # RSI 77 < 80 custom threshold — not high-risk for conservative
    result = engine.evaluate(_snap("77"), SignalSensitivity.CONSERVATIVE)
    assert result.sensitivity == SignalSensitivity.CONSERVATIVE
    assert result.risk_level != RiskLevel.HIGH_RISK


def test_resolve_rule_sets_returns_none_when_no_yaml_section():
    rs = _resolve_rule_sets({})
    assert rs is None


def test_resolve_rule_sets_returns_none_when_section_empty():
    # Empty sensitivities section → no overrides → None → RuleEngine uses its hardcoded defaults
    rs = _resolve_rule_sets({"risk_engine": {"sensitivities": {}}})
    assert rs is None


def test_resolve_rule_sets_reads_yaml_override():
    cfg = {"risk_engine": {"sensitivities": {"conservative": {"rsi_high_risk": 80}}}}
    rs = _resolve_rule_sets(cfg)
    assert rs is not None
    assert rs[SignalSensitivity.CONSERVATIVE].RSI_HIGH_RISK == Decimal("80")
    # Other presets keep their defaults
    assert rs[SignalSensitivity.BALANCED].RSI_HIGH_RISK == Decimal("70")
