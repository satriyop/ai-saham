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
from typing import Union

from src.application.ports.rules_loader import RulesLoader
from src.application.rules.schema import BUILTIN_INDICATORS, IndicatorType
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.aggregate_indicators_use_case import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import GateContext, RiskGate
from src.domain.rules.rule_engine import RuleEngine
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskLevel, RiskProfile
from src.domain.value_objects.sentiment import SentimentSnapshot


@dataclass
class AssessRiskRequest:
    """Request DTO for risk assessment."""

    ticker: str
    profile: str = "balanced"
    sma_period: int = 20
    ema_period: int = 20
    rsi_period: int = 14
    rules_file: Path | str | None = None  # Custom YAML rules file
    sentiment: SentimentSnapshot | None = None  # Optional sentiment context
    # Phase B: pre-loaded non-technical data for gate evaluation.
    # If provided and the use case has gates configured, gates run before
    # the technical rule engine (structural) and after (execution).
    gate_context: GateContext | None = None


@dataclass
class AssessRiskResponse:
    """Response DTO containing risk assessment result."""

    ticker: str
    assessment: RiskAssessment
    sma_period: int
    ema_period: int
    rsi_period: int
    coverage_warning: str | None = None

    @property
    def gate_triggered(self) -> str | None:
        """Delegates to RiskAssessment — single source of truth."""
        return self.assessment.gate_triggered

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
    coverage_warning: str | None = None


@dataclass
class AssessRiskTrendResponse:
    """Response DTO for risk trend over N days."""

    ticker: str
    profile: str
    history: list[tuple[date, str, int]]  # (date, risk_level, confidence)
    direction: str  # "IMPROVING" | "STABLE" | "DETERIORATING"
    days_in_current: int


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

    def __init__(
        self,
        repository: MarketDataRepository,
        registry: IndicatorRegistry | None = None,
        rules_loader: RulesLoader | None = None,
        structural_gates: list[RiskGate] | None = None,
        execution_gates: list[RiskGate] | None = None,
    ) -> None:
        """
        Initialize with repository, optional registry, optional rules loader,
        and optional risk gates.

        Args:
            repository: MarketDataRepository for fetching cached candles
            registry: IndicatorRegistry for computing indicators.
                     If None, creates default registry (built-ins only).
            rules_loader: RulesLoader port interface.
            structural_gates: Gates run BEFORE the rule engine (e.g. FundamentalGate,
                             LiquidityGate). If any fires, the rule engine is skipped.
                             Requires gate_context on the request.
            execution_gates: Gates run AFTER the rule engine (e.g. BandarGate).
                            Can downgrade but not upgrade the technical result.
                            Requires gate_context on the request.
        """
        self._repository = repository
        self._registry = registry if registry is not None else IndicatorRegistry()
        self._rule_engine = RuleEngine()
        if rules_loader is None:
            from src.infrastructure.config.yaml_loader import YamlConfigLoader

            rules_loader = YamlConfigLoader()
        self._rules_loader = rules_loader
        self._structural_gates: list[RiskGate] = structural_gates or []
        self._execution_gates: list[RiskGate] = execution_gates or []

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

            # Load rules with registry for indicator validation
            rule_set = self._rules_loader.load(request.rules_file, registry=self._registry)
            interpreter = YamlRuleInterpreter(rule_set)

            # Get required indicators from the rule set
            # Pass registry so it can resolve custom formulas (from config/formulas.yaml)
            required_indicators = interpreter.get_required_indicators(registry=self._registry)

            # Build snapshot with all required indicators
            latest_snapshot = self._build_snapshot_for_rules(
                ticker=request.ticker,
                required_indicators=required_indicators,
            )

            # Inject sentiment indicators if provided
            if request.sentiment:
                sentiment_extras = (
                    ("SENTIMENT_SCORE", Decimal(str(request.sentiment.score))),
                    ("SENTIMENT_LABEL", request.sentiment.overall_sentiment.name),
                    ("SENTIMENT_CATALYST", request.sentiment.primary_catalyst.name),
                )
                latest_snapshot = latest_snapshot.with_extras(sentiment_extras)

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
                    f"Run 'saham fetch market {request.ticker.upper()} --days 365' first."
                )

            latest_snapshot = agg_response.snapshots[-1]

            # Phase B: gate evaluation — build enriched context, then run gates.
            # Structural gates short-circuit before the rule engine;
            # execution gates may downgrade after.
            gate_ctx = self._build_gate_context(request, latest_snapshot.date)

            if gate_ctx is not None and self._structural_gates:
                for gate in self._structural_gates:
                    gate_result = gate.evaluate(gate_ctx, RiskLevel.MODERATE)
                    if gate_result.triggered and gate_result.override_risk is not None:
                        # Tier 1/2 structural gates: gate name propagates into the
                        # domain value object so ExplainRiskUseCase can narrate it.
                        assessment = RiskAssessment(
                            profile=RiskProfile.from_string(request.profile),
                            risk_level=gate_result.override_risk,
                            confidence=gate_result.confidence,
                            rationale=(gate_result.reason,),
                            snapshot_date=latest_snapshot.date,
                            indicators=latest_snapshot,
                            gate_triggered=type(gate).__name__,
                        )
                        return AssessRiskResponse(
                            ticker=agg_response.ticker,
                            assessment=assessment,
                            sma_period=request.sma_period,
                            ema_period=request.ema_period,
                            rsi_period=request.rsi_period,
                            coverage_warning=agg_response.coverage_warning,
                        )

            profile = RiskProfile.from_string(request.profile)
            assessment = self._rule_engine.evaluate(latest_snapshot, profile)

            if gate_ctx is not None and self._execution_gates:
                for gate in self._execution_gates:
                    gate_result = gate.evaluate(gate_ctx, assessment.risk_level)
                    if gate_result.triggered and gate_result.override_risk is not None:
                        # Tier 3 execution gates: downgrade; preserve prior rationale.
                        assessment = RiskAssessment(
                            profile=assessment.profile,
                            risk_level=gate_result.override_risk,
                            confidence=gate_result.confidence,
                            rationale=(*assessment.rationale, gate_result.reason),
                            snapshot_date=assessment.snapshot_date,
                            indicators=assessment.indicators,
                            gate_triggered=type(gate).__name__,
                        )
                        return AssessRiskResponse(
                            ticker=agg_response.ticker,
                            assessment=assessment,
                            sma_period=request.sma_period,
                            ema_period=request.ema_period,
                            rsi_period=request.rsi_period,
                            coverage_warning=agg_response.coverage_warning,
                        )

            return AssessRiskResponse(
                ticker=agg_response.ticker,
                assessment=assessment,
                sma_period=request.sma_period,
                ema_period=request.ema_period,
                rsi_period=request.rsi_period,
                coverage_warning=agg_response.coverage_warning,
            )

    def _build_gate_context(
        self,
        request: AssessRiskRequest,
        snapshot_date: date,
    ) -> GateContext | None:
        """
        Return an enriched GateContext for gate evaluation.

        If request.gate_context is None or no gates are configured, returns None.
        Enriches the caller-provided context with recent candles (for LiquidityGate)
        from the repository.
        """
        if request.gate_context is None:
            return None
        if not self._structural_gates and not self._execution_gates:
            return None

        ctx = request.gate_context
        # Enrich with candles for LiquidityGate only if not already provided
        if not ctx.recent_candles:
            from dataclasses import replace

            candles = self._repository.get_candles(request.ticker.upper())
            ctx = replace(ctx, recent_candles=tuple(candles[-20:]))
        return ctx

    def _build_snapshot_for_rules(
        self,
        ticker: str,
        required_indicators: dict[str, tuple[Union[IndicatorType, str], int]],
    ) -> IndicatorSnapshot:
        """
        Build an IndicatorSnapshot with all indicators required by the rules.

        Computes each indicator (built-in or plugin) with its specified period
        and returns a snapshot with built-in fields (sma, ema, rsi) plus extras
        for any custom-named indicators.

        Args:
            ticker: Stock ticker symbol
            required_indicators: Dict mapping indicator name to (type, period).
                                Type can be IndicatorType or string for plugins.

        Returns:
            IndicatorSnapshot with all required indicator values

        Raises:
            ValueError: If insufficient data for any indicator
        """
        ticker = ticker.upper().strip()
        if not ticker:
            raise ValueError("Ticker cannot be empty")

        # Fetch candles once (enough for all indicators)
        candles = self._repository.get_candles(ticker)
        if not candles:
            raise ValueError(
                f"Insufficient data for {ticker}. "
                f"Run 'saham fetch market {ticker} --days 365' first."
            )

        # Compute each required indicator using registry
        indicator_values: dict[str, tuple[date, Decimal]] = {}
        for name, (ind_type, period) in required_indicators.items():
            # Skip sentiment context indicators (they are injected later)
            if name in ("SENTIMENT_SCORE", "SENTIMENT_LABEL", "SENTIMENT_CATALYST"):
                continue

            # Get type name as string for registry
            type_name = (
                ind_type.value if isinstance(ind_type, IndicatorType) else ind_type
            )
            values = self._registry.compute(type_name, candles, period)
            if not values:
                raise ValueError(
                    f"Insufficient data to compute {name} ({type_name}, period={period})"
                )
            # Store the latest value
            indicator_values[name] = values[-1]

        # Use the earliest "latest" date among all computed indicators
        # Or today if no indicators computed (context only rules)
        if indicator_values:
            latest_date = min(d for d, _ in indicator_values.values())
        else:
            latest_date = date.today()

        # Build the snapshot
        # First, extract built-in indicator values (use defaults if not in required)
        sma_value = self._get_indicator_or_default(indicator_values, "SMA", candles)
        ema_value = self._get_indicator_or_default(indicator_values, "EMA", candles)
        rsi_value = self._get_indicator_or_default(indicator_values, "RSI", candles)

        # Build extras for custom-named indicators (not built-in names)
        extras: list[tuple[str, Decimal]] = []
        for name, (_, value) in indicator_values.items():
            if name not in BUILTIN_INDICATORS:
                extras.append((name, value))

        # Inject price fields (OPEN, HIGH, LOW, CLOSE, VOLUME) from the candle
        # at latest_date, so rules can reference CLOSE directly.
        candle_by_date = {c.date: c for c in candles}
        candle = candle_by_date.get(latest_date) or (candles[-1] if candles else None)
        if candle:
            extras.extend([
                ("OPEN", candle.open),
                ("HIGH", candle.high),
                ("LOW", candle.low),
                ("CLOSE", candle.close),
                ("VOLUME", Decimal(candle.volume)),
            ])

        return IndicatorSnapshot(
            date=latest_date,
            sma=sma_value,
            ema=ema_value,
            rsi=rsi_value,
            extras=tuple(extras),
        )

    def _get_indicator_or_default(
        self,
        indicator_values: dict[str, tuple[date, Decimal]],
        builtin_name: str,
        candles: list,
    ) -> Decimal:
        """Get indicator value from computed values or compute with default period."""
        if builtin_name in indicator_values:
            return indicator_values[builtin_name][1]

        # Compute with default period using registry
        default_period = self._registry.get_default_period(builtin_name)
        values = self._registry.compute(builtin_name, candles, default_period)
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
                f"Run 'saham fetch market {request.ticker.upper()} --days 365' first."
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
            coverage_warning=agg_response.coverage_warning,
        )

    def execute_trend(
        self, request: AssessRiskRequest, days: int = 7
    ) -> "AssessRiskTrendResponse":
        """
        Assess risk level trend over the last N trading days.

        Re-uses AggregateIndicatorsUseCase snapshots (no extra DB queries).

        Args:
            request: Standard risk request (profile applies)
            days: Number of recent snapshots to include in history

        Returns:
            AssessRiskTrendResponse with per-day history and direction
        """
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
                f"Run 'saham fetch market {request.ticker.upper()} --days 365' first."
            )

        profile = RiskProfile.from_string(request.profile)
        window = agg_response.snapshots[-days:]

        history: list[tuple[date, str, int]] = []
        for snapshot in window:
            assessment = self._rule_engine.evaluate(snapshot, profile)
            history.append((snapshot.date, assessment.risk_level_name, assessment.confidence))

        # Determine direction: compare first vs last risk level
        _rank = {"LOW_RISK": 0, "MODERATE": 1, "HIGH_RISK": 2}
        first_rank = _rank.get(history[0][1], 1) if history else 1
        last_rank = _rank.get(history[-1][1], 1) if history else 1

        if last_rank < first_rank:
            direction = "IMPROVING"
        elif last_rank > first_rank:
            direction = "DETERIORATING"
        else:
            direction = "STABLE"

        # Count consecutive days at current level
        current_level = history[-1][1] if history else ""
        days_in_current = 0
        for _, level, _ in reversed(history):
            if level == current_level:
                days_in_current += 1
            else:
                break

        return AssessRiskTrendResponse(
            ticker=agg_response.ticker,
            profile=request.profile,
            history=history,
            direction=direction,
            days_in_current=days_in_current,
        )
