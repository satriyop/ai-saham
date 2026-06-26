"""
AssessRisk use case - evaluate stock risk using indicator-based rules.

Orchestrates indicator aggregation and rule evaluation to produce
deterministic risk assessments for different risk profiles.

Layer: Application
Depends on: Domain rules, Domain value objects, AggregateIndicatorsUseCase
"""

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Union

from src.application.ports.rules_loader import RulesLoader
from src.application.rules.schema import BUILTIN_INDICATORS, IndicatorType
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.aggregate_indicators_use_case import (
    AggregateIndicatorsRequest,
    AggregateIndicatorsUseCase,
)
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import GateContext, RiskGate
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import SignalSensitivity
from src.domain.value_objects.sentiment import SentimentSnapshot

if TYPE_CHECKING:
    from src.application.services.indicator_evaluator import IndicatorEvaluator


@dataclass
class AssessRiskRequest:
    """Request DTO for risk assessment."""

    ticker: str
    sensitivity: str = "balanced"
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
        """Gate-based risk indicator for display."""
        if self.assessment.gate_triggered:
            return "BLOCKED"
        return "open"

    @property
    def confidence(self) -> int:
        """Confidence of the gate that fired (0 when none)."""
        return self.assessment.gate_confidence or 0

    @property
    def sensitivity(self) -> str:
        """Convenience property for signal sensitivity preset name."""
        return self.assessment.sensitivity_name

    # Backwards-compatibility alias
    @property
    def profile(self) -> str:
        return self.sensitivity


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
    sensitivity: str
    history: list[tuple[date, str, int]]  # (date, indicator_reading, confidence)
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
        indicator_evaluator: "IndicatorEvaluator | None" = None,
    ) -> None:
        """
        Initialize with repository, optional registry, optional rules loader,
        and optional risk gates.

        Args:
            repository: MarketDataRepository for fetching cached candles
            registry: IndicatorRegistry for computing indicators.
                     If None, creates default registry (built-ins only).
            rules_loader: RulesLoader port interface.
            structural_gates: Gates run first (e.g. FundamentalGate, LiquidityGate,
                             FreeFloatGate). If any fires → BLOCKED_STRUCTURAL.
                             Requires gate_context on the request.
            execution_gates: Gates run after structural (e.g. BandarGate,
                            TechnicalGate). If any fires → BLOCKED_EXECUTION.
                            Requires gate_context on the request.
            indicator_evaluator: Optional IndicatorEvaluator for computing
                            indicator readings (trend history, TechnicalGate).
        """
        self._repository = repository
        self._registry = registry if registry is not None else IndicatorRegistry()
        if rules_loader is None:
            from src.infrastructure.config.yaml_loader import YamlConfigLoader

            rules_loader = YamlConfigLoader()
        self._rules_loader = rules_loader
        self._structural_gates: list[RiskGate] = structural_gates or []
        self._execution_gates: list[RiskGate] = execution_gates or []
        self._indicator_evaluator = indicator_evaluator

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

            from src.domain.value_objects.risk_signal import RiskLevel

            risk_level, confidence, rationale = interpreter.evaluate(latest_snapshot)
            if risk_level == RiskLevel.HIGH_RISK:
                assessment = RiskAssessment(
                    sensitivity=interpreter.profile_name,
                    rationale=tuple(rationale),
                    snapshot_date=latest_snapshot.date,
                    indicators=latest_snapshot,
                    gate_triggered="custom_rule",
                    gate_is_structural=False,
                    gate_confidence=confidence,
                )
            else:
                assessment = RiskAssessment(
                    sensitivity=interpreter.profile_name,
                    rationale=tuple(rationale),
                    snapshot_date=latest_snapshot.date,
                    indicators=latest_snapshot,
                )

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
            sensitivity = SignalSensitivity.from_string(request.sensitivity)

            # Gate evaluation — build enriched context, then run gates.
            # Structural gates short-circuit first (BLOCKED_STRUCTURAL);
            # execution gates run after (BLOCKED_EXECUTION).
            gate_ctx = self._build_gate_context(
                request, latest_snapshot.date, latest_snapshot
            )

            if gate_ctx is not None:
                for gate in self._structural_gates:
                    gate_result = gate.evaluate(gate_ctx)
                    if gate_result.triggered:
                        return self._gate_response(
                            agg_response, request, sensitivity, latest_snapshot,
                            gate, gate_result, is_structural=True,
                        )
                for gate in self._execution_gates:
                    gate_result = gate.evaluate(gate_ctx)
                    if gate_result.triggered:
                        return self._gate_response(
                            agg_response, request, sensitivity, latest_snapshot,
                            gate, gate_result, is_structural=False,
                        )

            # No gate fired.
            assessment = RiskAssessment(
                sensitivity=sensitivity,
                rationale=("all gates passed",),
                snapshot_date=latest_snapshot.date,
                indicators=latest_snapshot,
                gate_triggered=None,
            )
            return AssessRiskResponse(
                ticker=agg_response.ticker,
                assessment=assessment,
                sma_period=request.sma_period,
                ema_period=request.ema_period,
                rsi_period=request.rsi_period,
                coverage_warning=agg_response.coverage_warning,
            )

    def _gate_response(
        self,
        agg_response,
        request: AssessRiskRequest,
        sensitivity: SignalSensitivity,
        latest_snapshot: IndicatorSnapshot,
        gate: RiskGate,
        gate_result,
        is_structural: bool,
    ) -> "AssessRiskResponse":
        assessment = RiskAssessment(
            sensitivity=sensitivity,
            rationale=(gate_result.reason,),
            snapshot_date=latest_snapshot.date,
            indicators=latest_snapshot,
            gate_triggered=type(gate).__name__,
            gate_is_structural=is_structural,
            gate_confidence=gate_result.confidence,
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
        latest_snapshot: IndicatorSnapshot | None = None,
    ) -> GateContext | None:
        """
        Return an enriched GateContext for gate evaluation.

        If request.gate_context is None or no gates are configured, returns None.
        Enriches the caller-provided context with recent candles (for LiquidityGate)
        from the repository and the latest indicator snapshot (for TechnicalGate).
        """
        if request.gate_context is None:
            return None
        if not self._structural_gates and not self._execution_gates:
            return None

        ctx = request.gate_context
        # Enrich with candles for LiquidityGate only if not already provided.
        # Use snapshot_date as end_date to prevent look-ahead in backtests.
        if not ctx.recent_candles:
            candles = self._repository.get_candles(
                request.ticker.upper(),
                end_date=snapshot_date,
            )
            ctx = replace(ctx, recent_candles=tuple(candles[-20:]))
        if latest_snapshot is not None and ctx.latest_snapshot is None:
            ctx = replace(ctx, latest_snapshot=latest_snapshot)
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
        gate_ctx = self._build_gate_context(
            request, latest_snapshot.date, latest_snapshot
        )

        # Without a rule engine, gates produce the same verdict for all
        # sensitivities — they no longer depend on an intermediate risk level.
        # Run gates once, then emit one assessment per sensitivity preset.
        fired_gate = None
        fired_result = None
        fired_structural = None
        if gate_ctx is not None:
            for gate in self._structural_gates:
                gate_result = gate.evaluate(gate_ctx)
                if gate_result.triggered:
                    fired_gate, fired_result, fired_structural = gate, gate_result, True
                    break
            if fired_gate is None:
                for gate in self._execution_gates:
                    gate_result = gate.evaluate(gate_ctx)
                    if gate_result.triggered:
                        fired_gate, fired_result, fired_structural = gate, gate_result, False
                        break

        assessments: list[RiskAssessment] = []
        for sensitivity in (
            SignalSensitivity.CONSERVATIVE,
            SignalSensitivity.BALANCED,
            SignalSensitivity.AGGRESSIVE,
        ):
            if fired_gate is not None:
                assessments.append(RiskAssessment(
                    sensitivity=sensitivity,
                    rationale=(fired_result.reason,),
                    snapshot_date=latest_snapshot.date,
                    indicators=latest_snapshot,
                    gate_triggered=type(fired_gate).__name__,
                    gate_is_structural=fired_structural,
                    gate_confidence=fired_result.confidence,
                ))
            else:
                assessments.append(RiskAssessment(
                    sensitivity=sensitivity,
                    rationale=("all gates passed",),
                    snapshot_date=latest_snapshot.date,
                    indicators=latest_snapshot,
                    gate_triggered=None,
                ))

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

        window = agg_response.snapshots[-days:]

        history: list[tuple[date, str, int]] = []
        if self._indicator_evaluator is not None:
            for snapshot in window:
                ctx = self._indicator_evaluator.evaluate(snapshot)
                history.append(
                    (snapshot.date, ctx.overall.value.upper(), ctx.confidence)
                )
        else:
            for snapshot in window:
                history.append((snapshot.date, "UNKNOWN", 0))

        # Determine direction: compare first vs last indicator reading
        _rank = {"BULLISH": 0, "NEUTRAL": 1, "BEARISH": 2}
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
            sensitivity=request.sensitivity,
            history=history,
            direction=direction,
            days_in_current=days_in_current,
        )
