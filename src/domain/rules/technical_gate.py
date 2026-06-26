"""TechnicalGate — optional execution gate for SMA/EMA/RSI conditions.

Off by default. Uses IndicatorEvaluator internally. Does not affect other gates.

Layer: Domain
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.indicators.indicator_reading import IndicatorReading
from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate

if TYPE_CHECKING:
    from src.application.services.indicator_evaluator import IndicatorEvaluator


@dataclass(frozen=True)
class TechnicalGateConfig:
    block_when_bearish: bool = True


class TechnicalGate(RiskGate):
    def __init__(
        self,
        evaluator: "IndicatorEvaluator",
        config: TechnicalGateConfig | None = None,
    ) -> None:
        self._evaluator = evaluator
        self._config = config or TechnicalGateConfig()

    def evaluate(self, context: GateContext) -> GateResult:
        if context.latest_snapshot is None:
            return GateResult(
                triggered=False,
                reason="no snapshot for technical gate",
                confidence=0,
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
            confidence=100,
        )
