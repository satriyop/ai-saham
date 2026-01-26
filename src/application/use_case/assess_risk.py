"""
AssessRisk use case - evaluate stock risk using indicator-based rules.

Orchestrates indicator aggregation and rule evaluation to produce
deterministic risk assessments for different risk profiles.

Layer: Application
Depends on: Domain rules, Domain value objects, AggregateIndicatorsUseCase
"""

from dataclasses import dataclass
from pathlib import Path

from src.application.use_case.aggregate_indicators import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.rule_engine import RuleEngine
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskProfile


@dataclass
class AssessRiskRequest:
    """Request DTO for risk assessment."""

    ticker: str
    profile: str = "balanced"
    sma_period: int = 20
    ema_period: int = 20
    rsi_period: int = 14
    rules_file: Path | str | None = None  # Custom YAML rules file


@dataclass
class AssessRiskResponse:
    """Response DTO containing risk assessment result."""

    ticker: str
    assessment: RiskAssessment
    sma_period: int
    ema_period: int
    rsi_period: int

    @property
    def risk_level(self) -> str:
        """Convenience property for risk level string."""
        return self.assessment.risk_level_name

    @property
    def confidence(self) -> int:
        """Convenience property for confidence score."""
        return self.assessment.confidence

    @property
    def profile(self) -> str:
        """Convenience property for profile name."""
        return self.assessment.profile_name


@dataclass
class AssessAllProfilesResponse:
    """Response DTO containing assessments for all profiles."""

    ticker: str
    assessments: list[RiskAssessment]
    sma_period: int
    ema_period: int
    rsi_period: int


class AssessRiskUseCase:
    """
    Use case for assessing stock risk using rule-based evaluation.

    This use case:
        1. Validates the request
        2. Retrieves aggregated indicators via AggregateIndicatorsUseCase
        3. Extracts the latest snapshot
        4. Evaluates the snapshot using RuleEngine
        5. Returns a RiskAssessment

    The evaluation is deterministic: same input -> same output.
    Works fully offline using cached market data.
    """

    def __init__(self, repository: MarketDataRepository) -> None:
        """
        Initialize with repository dependency.

        Args:
            repository: MarketDataRepository for fetching cached candles
        """
        self._repository = repository
        self._rule_engine = RuleEngine()

    def execute(self, request: AssessRiskRequest) -> AssessRiskResponse:
        """
        Execute risk assessment for a single profile or custom rules.

        If rules_file is provided, uses custom YAML rules instead of built-in profiles.

        Args:
            request: Contains ticker, profile, indicator periods, and optional rules_file

        Returns:
            AssessRiskResponse with the risk assessment

        Raises:
            ValueError: If ticker invalid, profile invalid, or insufficient data
            RulesFileError: If rules file not found (when rules_file specified)
            RulesSchemaError: If rules file has invalid syntax
            RulesValidationError: If rules file has invalid content
        """
        # Get aggregated indicators first (needed for both paths)
        agg_use_case = AggregateIndicatorsUseCase(self._repository)
        agg_response = agg_use_case.execute(
            AggregateIndicatorsRequest(
                ticker=request.ticker,
                sma_period=request.sma_period,
                ema_period=request.ema_period,
                rsi_period=request.rsi_period,
                days=365,  # Get enough data for indicator convergence
            )
        )

        if not agg_response.has_values:
            raise ValueError(
                f"Insufficient data for {request.ticker.upper()}. "
                f"Run 'saham fetch {request.ticker.upper()}' first."
            )

        # Extract latest snapshot
        latest_snapshot = agg_response.snapshots[-1]

        # Evaluate using custom rules or built-in profile
        if request.rules_file is not None:
            # Load and evaluate custom rules
            from src.application.rules.interpreter import YamlRuleInterpreter
            from src.infrastructure.config.yaml_loader import YamlConfigLoader

            rule_set = YamlConfigLoader.load(request.rules_file)
            interpreter = YamlRuleInterpreter(rule_set)
            self._rule_engine.register_custom_rules(interpreter)
            assessment = self._rule_engine.evaluate_custom(latest_snapshot)
        else:
            # Use built-in profile
            profile = RiskProfile.from_string(request.profile)
            assessment = self._rule_engine.evaluate(latest_snapshot, profile)

        return AssessRiskResponse(
            ticker=agg_response.ticker,
            assessment=assessment,
            sma_period=request.sma_period,
            ema_period=request.ema_period,
            rsi_period=request.rsi_period,
        )

    def execute_all_profiles(self, request: AssessRiskRequest) -> AssessAllProfilesResponse:
        """
        Execute risk assessment for all profiles.

        Args:
            request: Contains ticker and indicator periods (profile is ignored)

        Returns:
            AssessAllProfilesResponse with assessments for all profiles

        Raises:
            ValueError: If ticker invalid or insufficient data
        """
        # Get aggregated indicators
        agg_use_case = AggregateIndicatorsUseCase(self._repository)
        agg_response = agg_use_case.execute(
            AggregateIndicatorsRequest(
                ticker=request.ticker,
                sma_period=request.sma_period,
                ema_period=request.ema_period,
                rsi_period=request.rsi_period,
                days=365,
            )
        )

        if not agg_response.has_values:
            raise ValueError(
                f"Insufficient data for {request.ticker.upper()}. "
                f"Run 'saham fetch {request.ticker.upper()}' first."
            )

        # Extract latest snapshot
        latest_snapshot = agg_response.snapshots[-1]

        # Evaluate all profiles
        assessments = self._rule_engine.evaluate_all_profiles(latest_snapshot)

        return AssessAllProfilesResponse(
            ticker=agg_response.ticker,
            assessments=assessments,
            sma_period=request.sma_period,
            ema_period=request.ema_period,
            rsi_period=request.rsi_period,
        )
