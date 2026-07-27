"""Custom YAML rules evaluation path for risk assessment.

Layer: Application
Depends on: Domain rules, Domain value objects, RulesLoader port
"""

from datetime import date
from decimal import Decimal
from typing import Union

from src.application.dto.assess_risk import AssessRiskRequest, AssessRiskResponse
from src.application.ports.rules_loader import RulesLoader
from src.application.rules.interpreter import YamlRuleInterpreter
from src.application.rules.schema import BUILTIN_INDICATORS, IndicatorType
from src.application.services.indicator_registry import IndicatorRegistry
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.value_objects.indicator_snapshot import IndicatorSnapshot
from src.domain.value_objects.risk_assessment import RiskAssessment
from src.domain.value_objects.risk_signal import RiskLevel


class AssessRiskCustomRulesEvaluator:
    """Evaluates risk using a custom YAML rule set instead of configured gates."""

    def __init__(
        self,
        repository: MarketDataRepository,
        registry: IndicatorRegistry,
        rules_loader: RulesLoader,
        indicator_history_days: int,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._rules_loader = rules_loader
        self._indicator_history_days = indicator_history_days

    def evaluate(self, request: AssessRiskRequest) -> AssessRiskResponse:
        """
        Evaluate risk for a ticker using custom YAML rules.

        Args:
            request: Contains ticker, indicator periods, and rules_file

        Returns:
            AssessRiskResponse with the risk assessment

        Raises:
            ValueError: If ticker invalid or insufficient data
            RulesFileError: If rules file not found
            RulesSchemaError: If rules file has invalid syntax
            RulesValidationError: If rules file has invalid content
        """
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

        risk_level, confidence, rationale = interpreter.evaluate(latest_snapshot)
        if risk_level == RiskLevel.HIGH_RISK:
            assessment = RiskAssessment(
                rationale=tuple(rationale),
                snapshot_date=latest_snapshot.date,
                indicators=latest_snapshot,
                gate_triggered="custom_rule",
                gate_is_structural=False,
                gate_confidence=confidence,
            )
        else:
            assessment = RiskAssessment(
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
                f"Insufficient data for {ticker}. Run "
                f"'saham fetch market {ticker} --days "
                f"{self._indicator_history_days}' first."
            )

        # Compute each required indicator using registry
        indicator_values: dict[str, tuple[date, Decimal]] = {}
        for name, (ind_type, period) in required_indicators.items():
            # Skip sentiment context indicators (they are injected later)
            if name in ("SENTIMENT_SCORE", "SENTIMENT_LABEL", "SENTIMENT_CATALYST"):
                continue

            # Get type name as string for registry
            type_name = ind_type.value if isinstance(ind_type, IndicatorType) else ind_type
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
            extras.extend(
                [
                    ("OPEN", candle.open),
                    ("HIGH", candle.high),
                    ("LOW", candle.low),
                    ("CLOSE", candle.close),
                    ("VOLUME", Decimal(candle.volume)),
                ]
            )

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
