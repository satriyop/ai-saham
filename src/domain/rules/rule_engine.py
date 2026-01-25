"""
Rule engine for risk profile evaluation.

Orchestrates rule set selection and evaluation, producing
RiskAssessment value objects from indicator snapshots.

Layer: Domain
"""

from src.domain.rules.aggressive import AggressiveRuleSet
from src.domain.rules.balanced import BalancedRuleSet
from src.domain.rules.base_rule import BaseRule
from src.domain.rules.conservative import ConservativeRuleSet
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskProfile


class RuleEngine:
    """
    Orchestrates risk evaluation using profile-specific rule sets.

    Responsible for:
        1. Selecting the appropriate rule set based on profile
        2. Evaluating indicator snapshots against the selected rules
        3. Producing immutable RiskAssessment value objects

    This is a pure domain service with no I/O dependencies.
    """

    def __init__(self) -> None:
        """Initialize rule sets for all profiles."""
        self._rule_sets: dict[RiskProfile, BaseRule] = {
            RiskProfile.CONSERVATIVE: ConservativeRuleSet(),
            RiskProfile.BALANCED: BalancedRuleSet(),
            RiskProfile.AGGRESSIVE: AggressiveRuleSet(),
        }

    def evaluate(
        self,
        snapshot: IndicatorSnapshot,
        profile: RiskProfile | str,
    ) -> RiskAssessment:
        """
        Evaluate a snapshot against a specific risk profile.

        Args:
            snapshot: IndicatorSnapshot containing SMA, EMA, RSI values
            profile: RiskProfile enum or string (e.g., "balanced")

        Returns:
            RiskAssessment containing risk level, confidence, and rationale

        Raises:
            ValueError: If profile string is invalid
        """
        # Convert string to enum if needed
        if isinstance(profile, str):
            profile = RiskProfile.from_string(profile)

        # Get the appropriate rule set
        rule_set = self._rule_sets[profile]

        # Evaluate and get results
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        # Create immutable RiskAssessment
        return RiskAssessment(
            profile=profile,
            risk_level=risk_level,
            confidence=confidence,
            rationale=tuple(rationale),  # Convert to tuple for immutability
            snapshot_date=snapshot.date,
            indicators=snapshot,
        )

    def evaluate_all_profiles(
        self,
        snapshot: IndicatorSnapshot,
    ) -> list[RiskAssessment]:
        """
        Evaluate a snapshot against all risk profiles.

        Useful for comparing how different profiles interpret the same data.

        Args:
            snapshot: IndicatorSnapshot containing SMA, EMA, RSI values

        Returns:
            List of RiskAssessment, one for each profile
            (ordered: conservative, balanced, aggressive)
        """
        return [
            self.evaluate(snapshot, RiskProfile.CONSERVATIVE),
            self.evaluate(snapshot, RiskProfile.BALANCED),
            self.evaluate(snapshot, RiskProfile.AGGRESSIVE),
        ]

    @property
    def available_profiles(self) -> list[str]:
        """Return list of available profile names."""
        return [p.value for p in RiskProfile]
