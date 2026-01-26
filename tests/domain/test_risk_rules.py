"""
Tests for risk profile rule evaluation.

These tests verify:
- Each profile's thresholds are correctly applied
- Confidence scores are calculated correctly
- Rationale is generated for all conditions
- Determinism: same input -> same output

All tests run offline with no external dependencies.
"""

from datetime import date
from decimal import Decimal

import pytest

from src.domain.rules.aggressive import AggressiveRuleSet
from src.domain.rules.balanced import BalancedRuleSet
from src.domain.rules.conservative import ConservativeRuleSet
from src.domain.rules.rule_engine import RuleEngine
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskLevel, RiskProfile

# --- Test Fixtures ---


def make_snapshot(
    sma: str = "100.00",
    ema: str = "100.00",
    rsi: str = "50.00",
    snapshot_date: date | None = None,
) -> IndicatorSnapshot:
    """Create a test indicator snapshot."""
    return IndicatorSnapshot(
        date=snapshot_date or date.today(),
        sma=Decimal(sma),
        ema=Decimal(ema),
        rsi=Decimal(rsi),
    )


# --- Conservative Rule Tests ---


class TestConservativeRuleSet:
    """Test conservative profile rules."""

    def test_profile_name(self):
        """Conservative rule set should report correct profile name."""
        rule_set = ConservativeRuleSet()
        assert rule_set.profile_name == "conservative"

    def test_high_risk_requires_both_indicators(self):
        """Conservative HIGH_RISK requires RSI overbought AND downtrend."""
        rule_set = ConservativeRuleSet()

        # RSI > 75 AND EMA < SMA by >= 1%
        snapshot = make_snapshot(sma="100.00", ema="98.50", rsi="76.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 100
        assert any("Both indicators confirm HIGH_RISK" in r for r in rationale)

    def test_low_risk_requires_both_indicators(self):
        """Conservative LOW_RISK requires RSI oversold AND uptrend."""
        rule_set = ConservativeRuleSet()

        # RSI < 25 AND EMA > SMA by >= 1%
        snapshot = make_snapshot(sma="100.00", ema="101.50", rsi="24.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 100
        assert any("Both indicators confirm LOW_RISK" in r for r in rationale)

    def test_moderate_when_only_rsi_signals(self):
        """Conservative returns MODERATE when only RSI signals."""
        rule_set = ConservativeRuleSet()

        # RSI overbought but no significant trend
        snapshot = make_snapshot(sma="100.00", ema="100.50", rsi="80.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE
        assert confidence == 50  # One indicator active
        assert any(
            "do not agree" in r.lower() or "defaults to moderate" in r.lower()
            for r in rationale
        )

    def test_moderate_when_only_trend_signals(self):
        """Conservative returns MODERATE when only trend signals."""
        rule_set = ConservativeRuleSet()

        # Strong downtrend but neutral RSI
        snapshot = make_snapshot(sma="100.00", ema="97.00", rsi="50.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE
        assert confidence == 50  # One indicator active

    def test_moderate_when_both_neutral(self):
        """Conservative returns MODERATE with 0 confidence when both neutral."""
        rule_set = ConservativeRuleSet()

        # Neutral RSI, no significant trend
        snapshot = make_snapshot(sma="100.00", ema="100.00", rsi="50.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE
        assert confidence == 0

    def test_thresholds_are_correct(self):
        """Conservative thresholds should be RSI 75/25, divergence 1%."""
        rule_set = ConservativeRuleSet()

        assert rule_set.RSI_HIGH_RISK == Decimal("75")
        assert rule_set.RSI_LOW_RISK == Decimal("25")
        assert rule_set.DIVERGENCE_THRESHOLD == Decimal("1.0")


# --- Balanced Rule Tests ---


class TestBalancedRuleSet:
    """Test balanced profile rules."""

    def test_profile_name(self):
        """Balanced rule set should report correct profile name."""
        rule_set = BalancedRuleSet()
        assert rule_set.profile_name == "balanced"

    def test_high_risk_when_both_agree(self):
        """Balanced HIGH_RISK with both indicators agreeing -> 100% confidence."""
        rule_set = BalancedRuleSet()

        # RSI > 70 AND downtrend
        snapshot = make_snapshot(sma="100.00", ema="99.00", rsi="75.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 100

    def test_low_risk_when_both_agree(self):
        """Balanced LOW_RISK with both indicators agreeing -> 100% confidence."""
        rule_set = BalancedRuleSet()

        # RSI < 30 AND uptrend
        snapshot = make_snapshot(sma="100.00", ema="101.00", rsi="25.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 100

    def test_high_risk_when_only_rsi_signals(self):
        """Balanced HIGH_RISK with only RSI -> 50% confidence."""
        rule_set = BalancedRuleSet()

        # RSI overbought, neutral trend
        snapshot = make_snapshot(sma="100.00", ema="100.00", rsi="75.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 50

    def test_moderate_when_signals_conflict(self):
        """Balanced returns MODERATE when signals conflict."""
        rule_set = BalancedRuleSet()

        # RSI overbought (high-risk signal) but uptrend (low-risk signal)
        snapshot = make_snapshot(sma="100.00", ema="101.00", rsi="75.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE
        assert confidence == 50

    def test_moderate_when_both_neutral(self):
        """Balanced returns MODERATE with 0 confidence when both neutral."""
        rule_set = BalancedRuleSet()

        snapshot = make_snapshot(sma="100.00", ema="100.00", rsi="50.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.MODERATE
        assert confidence == 0

    def test_thresholds_are_correct(self):
        """Balanced thresholds should be RSI 70/30, no divergence minimum."""
        rule_set = BalancedRuleSet()

        assert rule_set.RSI_HIGH_RISK == Decimal("70")
        assert rule_set.RSI_LOW_RISK == Decimal("30")
        assert rule_set.DIVERGENCE_THRESHOLD == Decimal("0")


# --- Aggressive Rule Tests ---


class TestAggressiveRuleSet:
    """Test aggressive profile rules."""

    def test_profile_name(self):
        """Aggressive rule set should report correct profile name."""
        rule_set = AggressiveRuleSet()
        assert rule_set.profile_name == "aggressive"

    def test_high_risk_from_rsi_alone(self):
        """Aggressive HIGH_RISK from RSI alone -> 50% confidence."""
        rule_set = AggressiveRuleSet()

        # RSI > 60, neutral trend
        snapshot = make_snapshot(sma="100.00", ema="100.00", rsi="65.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 50

    def test_low_risk_from_rsi_alone(self):
        """Aggressive LOW_RISK from RSI alone -> 50% confidence."""
        rule_set = AggressiveRuleSet()

        # RSI < 40, neutral trend
        snapshot = make_snapshot(sma="100.00", ema="100.00", rsi="35.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 50

    def test_high_risk_from_trend_alone(self):
        """Aggressive HIGH_RISK from trend alone when RSI neutral."""
        rule_set = AggressiveRuleSet()

        # Neutral RSI but downtrend >= 0.1%
        snapshot = make_snapshot(sma="100.00", ema="99.80", rsi="50.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 50
        assert any("Trend alone" in r for r in rationale)

    def test_low_risk_from_trend_alone(self):
        """Aggressive LOW_RISK from trend alone when RSI neutral."""
        rule_set = AggressiveRuleSet()

        # Neutral RSI but uptrend >= 0.1%
        snapshot = make_snapshot(sma="100.00", ema="100.20", rsi="50.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.LOW_RISK
        assert confidence == 50
        assert any("Trend alone" in r for r in rationale)

    def test_high_risk_both_agree_full_confidence(self):
        """Aggressive HIGH_RISK with both agreeing -> 100% confidence."""
        rule_set = AggressiveRuleSet()

        # RSI > 60 AND downtrend
        snapshot = make_snapshot(sma="100.00", ema="99.50", rsi="65.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 100

    def test_rsi_takes_priority_over_conflicting_trend(self):
        """Aggressive: RSI signal takes priority when trend disagrees."""
        rule_set = AggressiveRuleSet()

        # RSI overbought but uptrend
        snapshot = make_snapshot(sma="100.00", ema="101.00", rsi="65.00")
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        assert risk_level == RiskLevel.HIGH_RISK
        assert confidence == 50
        assert any("trend disagrees" in r.lower() for r in rationale)

    def test_thresholds_are_correct(self):
        """Aggressive thresholds should be RSI 60/40, divergence 0.1%."""
        rule_set = AggressiveRuleSet()

        assert rule_set.RSI_HIGH_RISK == Decimal("60")
        assert rule_set.RSI_LOW_RISK == Decimal("40")
        assert rule_set.DIVERGENCE_THRESHOLD == Decimal("0.1")


# --- Rule Engine Tests ---


class TestRuleEngine:
    """Test RuleEngine orchestrator."""

    def test_evaluate_with_string_profile(self):
        """Engine should accept string profile names."""
        engine = RuleEngine()
        snapshot = make_snapshot()

        assessment = engine.evaluate(snapshot, "balanced")

        assert isinstance(assessment, RiskAssessment)
        assert assessment.profile == RiskProfile.BALANCED

    def test_evaluate_with_enum_profile(self):
        """Engine should accept RiskProfile enum."""
        engine = RuleEngine()
        snapshot = make_snapshot()

        assessment = engine.evaluate(snapshot, RiskProfile.CONSERVATIVE)

        assert assessment.profile == RiskProfile.CONSERVATIVE

    def test_evaluate_invalid_profile_raises_error(self):
        """Engine should raise ValueError for invalid profile."""
        engine = RuleEngine()
        snapshot = make_snapshot()

        with pytest.raises(ValueError, match="Invalid profile"):
            engine.evaluate(snapshot, "invalid_profile")

    def test_evaluate_all_profiles(self):
        """Engine should evaluate all profiles."""
        engine = RuleEngine()
        snapshot = make_snapshot()

        assessments = engine.evaluate_all_profiles(snapshot)

        assert len(assessments) == 3
        profiles = [a.profile for a in assessments]
        assert RiskProfile.CONSERVATIVE in profiles
        assert RiskProfile.BALANCED in profiles
        assert RiskProfile.AGGRESSIVE in profiles

    def test_available_profiles(self):
        """Engine should list available profiles."""
        engine = RuleEngine()

        profiles = engine.available_profiles

        assert "conservative" in profiles
        assert "balanced" in profiles
        assert "aggressive" in profiles

    def test_assessment_has_correct_snapshot_date(self):
        """Assessment should contain the correct snapshot date."""
        engine = RuleEngine()
        test_date = date(2024, 1, 15)
        snapshot = make_snapshot(snapshot_date=test_date)

        assessment = engine.evaluate(snapshot, "balanced")

        assert assessment.snapshot_date == test_date

    def test_assessment_has_indicators(self):
        """Assessment should contain the indicator snapshot."""
        engine = RuleEngine()
        snapshot = make_snapshot(sma="100.00", ema="105.00", rsi="45.00")

        assessment = engine.evaluate(snapshot, "balanced")

        assert assessment.indicators == snapshot


# --- Determinism Tests ---


class TestDeterminism:
    """Test that same input always produces same output."""

    def test_conservative_deterministic(self):
        """Conservative rules should be deterministic."""
        rule_set = ConservativeRuleSet()
        snapshot = make_snapshot(sma="100.00", ema="98.00", rsi="80.00")

        result1 = rule_set.evaluate(snapshot)
        result2 = rule_set.evaluate(snapshot)

        assert result1 == result2

    def test_balanced_deterministic(self):
        """Balanced rules should be deterministic."""
        rule_set = BalancedRuleSet()
        snapshot = make_snapshot(sma="100.00", ema="102.00", rsi="28.00")

        result1 = rule_set.evaluate(snapshot)
        result2 = rule_set.evaluate(snapshot)

        assert result1 == result2

    def test_aggressive_deterministic(self):
        """Aggressive rules should be deterministic."""
        rule_set = AggressiveRuleSet()
        snapshot = make_snapshot(sma="100.00", ema="100.50", rsi="55.00")

        result1 = rule_set.evaluate(snapshot)
        result2 = rule_set.evaluate(snapshot)

        assert result1 == result2

    def test_engine_deterministic(self):
        """Rule engine should produce deterministic assessments."""
        engine = RuleEngine()
        snapshot = make_snapshot(sma="100.00", ema="99.00", rsi="72.00")

        assessment1 = engine.evaluate(snapshot, "balanced")
        assessment2 = engine.evaluate(snapshot, "balanced")

        assert assessment1.risk_level == assessment2.risk_level
        assert assessment1.confidence == assessment2.confidence
        assert assessment1.rationale == assessment2.rationale


# --- Rationale Tests ---


class TestRationale:
    """Test that rationale is generated correctly."""

    def test_rationale_includes_rsi_explanation(self):
        """Rationale should explain RSI condition."""
        rule_set = BalancedRuleSet()
        snapshot = make_snapshot(rsi="75.50")

        _, _, rationale = rule_set.evaluate(snapshot)

        assert any("RSI 75.50" in r for r in rationale)
        assert any("high-risk threshold" in r.lower() for r in rationale)

    def test_rationale_includes_trend_explanation(self):
        """Rationale should explain trend condition."""
        rule_set = BalancedRuleSet()
        snapshot = make_snapshot(sma="100.00", ema="102.00")

        _, _, rationale = rule_set.evaluate(snapshot)

        assert any("uptrend" in r.lower() or "ema > sma" in r.lower() for r in rationale)

    def test_rationale_includes_profile_specific_thresholds(self):
        """Rationale should reference profile-specific thresholds."""
        conservative = ConservativeRuleSet()
        aggressive = AggressiveRuleSet()
        snapshot = make_snapshot(rsi="65.00")

        _, _, cons_rationale = conservative.evaluate(snapshot)
        _, _, agg_rationale = aggressive.evaluate(snapshot)

        # Conservative should mention 75 threshold (neutral for 65)
        assert any("75" in r for r in cons_rationale)
        # Aggressive should mention 60 threshold (triggered for 65)
        assert any("60" in r for r in agg_rationale)


# --- RiskAssessment Value Object Tests ---


class TestRiskAssessment:
    """Test RiskAssessment value object."""

    def test_assessment_is_immutable(self):
        """RiskAssessment should be frozen (immutable)."""
        engine = RuleEngine()
        snapshot = make_snapshot()
        assessment = engine.evaluate(snapshot, "balanced")

        with pytest.raises(Exception):  # FrozenInstanceError
            assessment.confidence = 999

    def test_confidence_validation(self):
        """RiskAssessment should validate confidence range."""
        snapshot = make_snapshot()

        with pytest.raises(ValueError, match="Confidence must be 0-100"):
            RiskAssessment(
                profile=RiskProfile.BALANCED,
                risk_level=RiskLevel.MODERATE,
                confidence=150,  # Invalid
                rationale=("test",),
                snapshot_date=date.today(),
                indicators=snapshot,
            )

    def test_profile_name_property(self):
        """RiskAssessment should expose profile name."""
        engine = RuleEngine()
        snapshot = make_snapshot()
        assessment = engine.evaluate(snapshot, "balanced")

        assert assessment.profile_name == "balanced"

    def test_risk_level_name_property(self):
        """RiskAssessment should expose risk level name in uppercase."""
        engine = RuleEngine()
        snapshot = make_snapshot()
        assessment = engine.evaluate(snapshot, "balanced")

        # Should be uppercase
        assert assessment.risk_level_name in ["HIGH_RISK", "MODERATE", "LOW_RISK"]

    def test_rationale_list_property(self):
        """RiskAssessment rationale_list should return mutable list."""
        engine = RuleEngine()
        snapshot = make_snapshot()
        assessment = engine.evaluate(snapshot, "balanced")

        rationale = assessment.rationale_list
        assert isinstance(rationale, list)
        # Original tuple should be unchanged even if list is modified
        rationale.append("extra")
        assert "extra" not in assessment.rationale


# --- RiskProfile Enum Tests ---


class TestRiskProfile:
    """Test RiskProfile enum."""

    def test_from_string_valid(self):
        """from_string should parse valid profile names."""
        assert RiskProfile.from_string("conservative") == RiskProfile.CONSERVATIVE
        assert RiskProfile.from_string("balanced") == RiskProfile.BALANCED
        assert RiskProfile.from_string("aggressive") == RiskProfile.AGGRESSIVE

    def test_from_string_case_insensitive(self):
        """from_string should be case insensitive."""
        assert RiskProfile.from_string("BALANCED") == RiskProfile.BALANCED
        assert RiskProfile.from_string("Balanced") == RiskProfile.BALANCED

    def test_from_string_strips_whitespace(self):
        """from_string should strip whitespace."""
        assert RiskProfile.from_string("  balanced  ") == RiskProfile.BALANCED

    def test_from_string_invalid_raises_error(self):
        """from_string should raise ValueError for invalid input."""
        with pytest.raises(ValueError, match="Invalid profile"):
            RiskProfile.from_string("invalid")
