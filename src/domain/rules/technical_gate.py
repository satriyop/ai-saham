"""TechnicalGate — optional execution gate for SMA/EMA/RSI conditions.

Off by default. Uses IndicatorEvaluator internally. Does not affect other gates.

Layer: Domain
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.indicators.indicator_reading import IndicatorReading
from src.domain.ports.indicator_evaluator import IndicatorEvaluator
from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate


@dataclass(frozen=True)
class TechnicalGateConfig:
    block_when_bearish: bool = True
    missing_data_action: str = "skip"
    missing_data_confidence: int = 0
    pass_confidence: int = 100


class TechnicalGate(RiskGate):
    def __init__(
        self,
        evaluator: IndicatorEvaluator,
        config: TechnicalGateConfig | None = None,
    ) -> None:
        self._evaluator = evaluator
        self._config = config or TechnicalGateConfig()

    def evaluate(self, context: GateContext) -> GateResult:
        if context.latest_snapshot is None:
            blocks = self._config.missing_data_action == "block"
            return GateResult.unevaluable(
                reason=(
                    "no snapshot for technical gate — blocked"
                    if blocks
                    else "no snapshot for technical gate"
                ),
                confidence=self._config.missing_data_confidence,
                blocks=blocks,
            )
        indicator_ctx = self._evaluator.evaluate(context.latest_snapshot)
        if self._config.block_when_bearish and indicator_ctx.overall == IndicatorReading.BEARISH:
            return GateResult(
                triggered=True,
                reason=(
                    f"technical: {indicator_ctx.overall.value}, "
                    f"RSI {float(indicator_ctx.rsi_value):.0f}, "
                    f"alignment {indicator_ctx.confidence}%"
                ),
                confidence=indicator_ctx.confidence,
            )
        return GateResult(
            triggered=False,
            reason=f"technical: {indicator_ctx.overall.value} (no block)",
            confidence=self._config.pass_confidence,
        )
