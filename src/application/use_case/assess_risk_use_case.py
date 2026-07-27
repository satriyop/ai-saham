"""AssessRisk use case - evaluate stock risk using deterministic gates.

Layer: Application
Depends on: Domain rules, Domain value objects, AggregateIndicatorsUseCase
"""

from typing import TYPE_CHECKING

from src.application.dto.assess_risk import (
    AssessRiskRequest,
    AssessRiskResponse,
    AssessRiskTrendResponse,
)
from src.application.ports.rules_loader import RulesLoader
from src.application.services.indicator_registry import IndicatorRegistry
from src.application.use_case.assess_risk_custom_rules_evaluator import (
    AssessRiskCustomRulesEvaluator,
)
from src.application.use_case.assess_risk_gate_evaluator import AssessRiskGateEvaluator
from src.application.use_case.assess_risk_trend_use_case import AssessRiskTrendUseCase
from src.domain.ports.market_data_repository import MarketDataRepository
from src.domain.rules.risk_gate import RiskGate

if TYPE_CHECKING:
    from src.application.services.indicator_evaluator import IndicatorEvaluator

__all__ = [
    "AssessRiskRequest",
    "AssessRiskResponse",
    "AssessRiskTrendResponse",
    "AssessRiskUseCase",
]


class AssessRiskUseCase:
    """
    Use case for assessing stock risk using rule-based evaluation.

    Orchestrates two mutually exclusive evaluation paths:
        - Custom YAML rules (when request.rules_file is set), delegated to
          AssessRiskCustomRulesEvaluator.
        - Standard configured structural/execution gates, delegated to
          AssessRiskGateEvaluator.

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
        indicator_history_days: int = 365,
        gate_recent_candle_lookback: int = 20,
    ) -> None:
        """
        Initialize with repository, optional registry, optional rules loader,
        and optional risk gates.

        Args:
            repository: MarketDataRepository for fetching cached candles
            registry: IndicatorRegistry for computing indicators.
                     If None, creates default registry (built-ins only).
            rules_loader: RulesLoader port interface. Required only when
                         requests set rules_file (custom rules mode); must
                         be injected by the caller's adapter/factory.
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
        self._rules_loader = rules_loader
        self._indicator_evaluator = indicator_evaluator
        self._indicator_history_days = indicator_history_days
        self._gate_recent_candle_lookback = gate_recent_candle_lookback
        self._gate_evaluator = AssessRiskGateEvaluator(
            repository=repository,
            structural_gates=structural_gates or [],
            execution_gates=execution_gates or [],
            indicator_history_days=indicator_history_days,
            gate_recent_candle_lookback=gate_recent_candle_lookback,
        )
        self._trend_use_case = AssessRiskTrendUseCase(
            repository=repository,
            indicator_evaluator=indicator_evaluator,
            indicator_history_days=indicator_history_days,
        )

    def execute(self, request: AssessRiskRequest) -> AssessRiskResponse:
        """
        Execute risk assessment for a ticker.

        If rules_file is provided, uses custom YAML rules instead of configured risk gates.

        Args:
            request: Contains ticker, indicator periods, and optional rules_file

        Returns:
            AssessRiskResponse with the risk assessment

        Raises:
            ValueError: If ticker invalid, insufficient data, or rules_file is
                        requested without an injected rules_loader
            RulesFileError: If rules file not found (when rules_file specified)
            RulesSchemaError: If rules file has invalid syntax
            RulesValidationError: If rules file has invalid content
        """
        if request.rules_file is not None:
            if self._rules_loader is None:
                raise ValueError("rules_loader is required when rules_file is provided")
            custom_rules_evaluator = AssessRiskCustomRulesEvaluator(
                repository=self._repository,
                registry=self._registry,
                rules_loader=self._rules_loader,
                indicator_history_days=self._indicator_history_days,
            )
            return custom_rules_evaluator.evaluate(request)
        return self._gate_evaluator.evaluate(request)

    def execute_trend(self, request: AssessRiskRequest, days: int = 7) -> "AssessRiskTrendResponse":
        """Assess risk level trend over the last N trading days."""
        return self._trend_use_case.execute(request, days=days)
