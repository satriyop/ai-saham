"""
BandarGate — execution gate for institutional distribution conflict (Rec 5).

In IDX, 'bandar' (institutional operators / big players) accumulation or
distribution heavily determines whether technical breakouts succeed. Retail
traders following technical signals can be caught in a distribution trap where
institutions are quietly selling into retail demand (pump & dump dynamics).

This gate fires when the 5-day bandar flow shows active distribution —
preventing entry into a retail trap even when the RSI and moving averages
appear constructive.

Layer: Domain
"""

from dataclasses import dataclass, field

from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate

# Labels from BandarDetectorSnapshot that indicate distribution
_DEFAULT_DISTRIBUTION_LABELS = frozenset(
    {
        "Small Dist",
        "Big Dist",
    }
)


@dataclass(frozen=True)
class BandarGateConfig:
    distribution_labels: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_DISTRIBUTION_LABELS
    )
    missing_data_action: str = "skip"
    missing_data_confidence: int = 0
    triggered_confidence: int = 80
    pass_confidence: int = 100


class BandarGate(RiskGate):
    """
    Execution gate: bandar 5-day distribution present.

    Fires unconditionally when distribution is present in the 5-day flow.
    With no bandar flow data the result is ``GateOutcome.UNEVALUABLE``; whether
    that also blocks is governed by ``BandarGateConfig.missing_data_action``.
    """

    def __init__(self, config: BandarGateConfig | None = None) -> None:
        self._config = config or BandarGateConfig()

    def evaluate(self, context: GateContext) -> GateResult:
        if context.five_day_accdist is None:
            blocks = self._config.missing_data_action == "block"
            return GateResult.unevaluable(
                reason=(
                    "no bandar flow data — gate blocked"
                    if blocks
                    else "no bandar flow data — gate skipped"
                ),
                confidence=self._config.missing_data_confidence,
                blocks=blocks,
            )
        if context.five_day_accdist in self._config.distribution_labels:
            return GateResult(
                triggered=True,
                reason=(
                    f"Bandar distribution ({context.five_day_accdist}) — distribution trap risk"
                ),
                confidence=self._config.triggered_confidence,
            )
        return GateResult(
            triggered=False,
            reason=f"Bandar 5-day ({context.five_day_accdist}) consistent",
            confidence=self._config.pass_confidence,
        )
