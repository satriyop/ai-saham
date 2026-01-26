"""
AssessRisk use case - evaluate stock risk using indicator-based rules.

Orchestrates indicator aggregation and rule evaluation to produce
deterministic risk assessments for different risk profiles.

Layer: Application
Depends on: Domain rules, Domain value objects, AggregateIndicatorsUseCase
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.application.rules.schema import BUILTIN_INDICATORS, IndicatorType
from src.application.use_case.aggregate_indicators import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.domain.indicators import calculate_ema, calculate_rsi, calculate_sma
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.rule_engine import RuleEngine
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
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
        # Evaluate using custom rules or built-in profile
        if request.rules_file is not None:
            # Load and evaluate custom rules
            from src.application.rules.interpreter import YamlRuleInterpreter
            from src.infrastructure.config.yaml_loader import YamlConfigLoader

            rule_set = YamlConfigLoader.load(request.rules_file)
            interpreter = YamlRuleInterpreter(rule_set)

            # Get required indicators from the rule set
            required_indicators = interpreter.get_required_indicators()

            # Build snapshot with all required indicators
            latest_snapshot = self._build_snapshot_for_rules(
                ticker=request.ticker,
                required_indicators=required_indicators,
            )

            self._rule_engine.register_custom_rules(interpreter)
            assessment = self._rule_engine.evaluate_custom(latest_snapshot)

            return AssessRiskResponse(
                ticker=request.ticker.upper(),
                assessment=assessment,
                sma_period=request.sma_period,
                ema_period=request.ema_period,
                rsi_period=request.rsi_period,
            )
        else:
            # Use built-in profile - standard aggregation flow
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

            latest_snapshot = agg_response.snapshots[-1]

            profile = RiskProfile.from_string(request.profile)
            assessment = self._rule_engine.evaluate(latest_snapshot, profile)

            return AssessRiskResponse(
                ticker=agg_response.ticker,
                assessment=assessment,
                sma_period=request.sma_period,
                ema_period=request.ema_period,
                rsi_period=request.rsi_period,
            )

    def _build_snapshot_for_rules(
        self,
        ticker: str,
        required_indicators: dict[str, tuple[IndicatorType, int]],
    ) -> IndicatorSnapshot:
        """
        Build an IndicatorSnapshot with all indicators required by the rules.

        Computes each indicator with its specified period and returns
        a snapshot with built-in fields (sma, ema, rsi) plus extras
        for any custom-named indicators.

        Args:
            ticker: Stock ticker symbol
            required_indicators: Dict mapping indicator name to (type, period)

        Returns:
            IndicatorSnapshot with all required indicator values

        Raises:
            ValueError: If insufficient data for any indicator
        """
        ticker = ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")

        # Fetch candles once (enough for all indicators)
        candles = self._repository.get_candles(ticker, days=365)
        if not candles:
            raise ValueError(
                f"Insufficient data for {ticker}. "
                f"Run 'saham fetch {ticker}' first."
            )

        # Compute each required indicator
        indicator_values: dict[str, tuple[date, Decimal]] = {}
        for name, (ind_type, period) in required_indicators.items():
            values = self._compute_indicator(candles, ind_type, period)
            if not values:
                raise ValueError(
                    f"Insufficient data to compute {name} ({ind_type.value}, period={period})"
                )
            # Store the latest value
            indicator_values[name] = values[-1]

        # Find the most recent date common to all indicators
        if not indicator_values:
            raise ValueError("No indicators required by rules")

        # For simplicity, use the earliest "latest" date among all indicators
        # This ensures all indicator values are from the same date or earlier
        latest_date = min(d for d, _ in indicator_values.values())

        # Get values for this date (or the closest available)
        # For now, we use the last computed value for each indicator
        # In production, you might want stricter date alignment

        # Build the snapshot
        # First, extract built-in indicator values (use defaults if not in required)
        sma_value = self._get_indicator_or_default(
            indicator_values, "SMA", IndicatorType.SMA, candles
        )
        ema_value = self._get_indicator_or_default(
            indicator_values, "EMA", IndicatorType.EMA, candles
        )
        rsi_value = self._get_indicator_or_default(
            indicator_values, "RSI", IndicatorType.RSI, candles
        )

        # Build extras for custom-named indicators (not built-in names)
        extras: list[tuple[str, Decimal]] = []
        for name, (_, value) in indicator_values.items():
            if name not in BUILTIN_INDICATORS:
                extras.append((name, value))

        return IndicatorSnapshot(
            date=latest_date,
            sma=sma_value,
            ema=ema_value,
            rsi=rsi_value,
            extras=tuple(extras),
        )

    def _compute_indicator(
        self,
        candles: list,
        ind_type: IndicatorType,
        period: int,
    ) -> list[tuple[date, Decimal]]:
        """Compute indicator values using domain functions."""
        if ind_type == IndicatorType.SMA:
            return calculate_sma(candles, period=period)
        elif ind_type == IndicatorType.EMA:
            return calculate_ema(candles, period=period)
        elif ind_type == IndicatorType.RSI:
            return calculate_rsi(candles, period=period)
        else:
            raise ValueError(f"Unknown indicator type: {ind_type}")

    def _get_indicator_or_default(
        self,
        indicator_values: dict[str, tuple[date, Decimal]],
        builtin_name: str,
        ind_type: IndicatorType,
        candles: list,
    ) -> Decimal:
        """Get indicator value from computed values or compute with default period."""
        if builtin_name in indicator_values:
            return indicator_values[builtin_name][1]

        # Compute with default period
        _, default_period = BUILTIN_INDICATORS[builtin_name]
        values = self._compute_indicator(candles, ind_type, default_period)
        if values:
            return values[-1][1]
        return Decimal("0")  # Fallback if insufficient data

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
