"""
Rule engine for risk profile evaluation.

Orchestrates rule set selection and evaluation, producing
RiskAssessment value objects from indicator snapshots.

Layer: Domain
"""

from typing import TYPE_CHECKING

from src.domain.rules.aggressive import AggressiveRuleSet
from src.domain.rules.balanced import BalancedRuleSet
from src.domain.rules.base_rule import BaseRule
from src.domain.rules.conservative import ConservativeRuleSet
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import SignalSensitivity

if TYPE_CHECKING:
    from src.application.rules.interpreter import YamlRuleInterpreter


class RuleEngine:
    """
    Orchestrates rule evaluation using sensitivity-preset-specific rule sets.

    Responsible for:
        1. Selecting the appropriate rule set based on signal sensitivity preset
        2. Evaluating indicator snapshots against the selected rules
        3. Producing immutable RiskAssessment value objects
        4. Supporting custom YAML-based rules via register_custom_rules()

    This is a pure domain service with no I/O dependencies.
    """

    def __init__(
        self,
        rule_sets: "dict[SignalSensitivity, BaseRule] | None" = None,
    ) -> None:
        """Initialize rule sets for all signal sensitivity presets.

        Args:
            rule_sets: Optional pre-built rule sets with custom thresholds.
                       If None, defaults are used (hardcoded IDX-conventional values).
        """
        self._rule_sets: dict[SignalSensitivity, BaseRule] = rule_sets if rule_sets is not None else {
            SignalSensitivity.CONSERVATIVE: ConservativeRuleSet(),
            SignalSensitivity.BALANCED: BalancedRuleSet(),
            SignalSensitivity.AGGRESSIVE: AggressiveRuleSet(),
        }
        self._custom_interpreter: "YamlRuleInterpreter | None" = None

    def register_custom_rules(self, interpreter: "YamlRuleInterpreter") -> None:
        """Register a custom YAML-based rules interpreter.

        Once registered, use evaluate_custom() to evaluate against the
        custom rules instead of the built-in profiles.

        Args:
            interpreter: YamlRuleInterpreter instance loaded with custom rules
        """
        self._custom_interpreter = interpreter

    def has_custom_rules(self) -> bool:
        """Return True if custom rules have been registered."""
        return self._custom_interpreter is not None

    def evaluate_custom(self, snapshot: IndicatorSnapshot) -> RiskAssessment:
        """
        Evaluate a snapshot using custom YAML rules.

        Returns RiskAssessment with profile set to the rule set name (string).
        This is a separate method to preserve the existing evaluate() signature.

        Args:
            snapshot: IndicatorSnapshot containing SMA, EMA, RSI values

        Returns:
            RiskAssessment with profile as string (rule set name)

        Raises:
            ValueError: If no custom rules have been registered
        """
        if self._custom_interpreter is None:
            raise ValueError(
                "No custom rules loaded. Use --rules-file to specify a rules file."
            )

        # Evaluate using the custom interpreter
        risk_level, confidence, rationale = self._custom_interpreter.evaluate(snapshot)

        # Create RiskAssessment with string profile (not SignalSensitivity enum)
        return RiskAssessment(
            sensitivity=self._custom_interpreter.profile_name,  # String, not enum
            risk_level=risk_level,
            confidence=confidence,
            rationale=tuple(rationale),
            snapshot_date=snapshot.date,
            indicators=snapshot,
        )

    def evaluate(
        self,
        snapshot: IndicatorSnapshot,
        profile: SignalSensitivity | str,
    ) -> RiskAssessment:
        """
        Evaluate a snapshot against a specific risk profile.

        Args:
            snapshot: IndicatorSnapshot containing SMA, EMA, RSI values
            profile: SignalSensitivity enum or string (e.g., "balanced")

        Returns:
            RiskAssessment containing risk level, confidence, and rationale

        Raises:
            ValueError: If profile string is invalid
        """
        # Convert string to enum if needed
        if isinstance(profile, str):
            profile = SignalSensitivity.from_string(profile)

        # Get the appropriate rule set
        rule_set = self._rule_sets[profile]

        # Evaluate and get results
        risk_level, confidence, rationale = rule_set.evaluate(snapshot)

        # Create immutable RiskAssessment
        return RiskAssessment(
            sensitivity=profile,
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
            self.evaluate(snapshot, SignalSensitivity.CONSERVATIVE),
            self.evaluate(snapshot, SignalSensitivity.BALANCED),
            self.evaluate(snapshot, SignalSensitivity.AGGRESSIVE),
        ]

    @property
    def available_sensitivities(self) -> list[str]:
        """Return list of available signal sensitivity preset names."""
        return [p.value for p in SignalSensitivity]

    # Backwards-compatibility alias
    @property
    def available_profiles(self) -> list[str]:
        return self.available_sensitivities
