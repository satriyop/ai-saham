"""
FundamentalGate — structural gate for financial distress detection (Rec 4).

Piotroski F-Score (0–9) measures profitability, leverage, and operational
efficiency from financial statements. Score ≤ 3 indicates a company under
financial stress — buying a technically-oversold signal on such a stock
risks catching a fundamental falling knife (value trap).

IDX context: local stocks can appear technically oversold while deteriorating
fundamentally — especially in cyclical sectors (coal, metals) during commodity
downturns. This gate prevents the technical engine from recommending entry
into distressed companies.

Layer: Domain
"""

from dataclasses import dataclass

from src.domain.rules.risk_gate import GateContext, GateResult, RiskGate

_DEFAULT_DISTRESS_THRESHOLD = 3


@dataclass(frozen=True)
class FundamentalGatePolicy:
    missing_data_action: str = "skip"
    missing_data_confidence: int = 0
    triggered_confidence: int = 100
    pass_confidence: int = 100


class FundamentalGate(RiskGate):
    """
    Structural gate: Piotroski F-score ≤ threshold fires.

    Runs before execution gates and short-circuits regardless of the current
    RSI or trend signal. No fundamental data available → gate passes silently.
    """

    def __init__(
        self,
        distress_threshold: int = _DEFAULT_DISTRESS_THRESHOLD,
        policy: FundamentalGatePolicy | None = None,
    ) -> None:
        if not 0 <= distress_threshold <= 9:
            raise ValueError(f"distress_threshold must be 0–9, got {distress_threshold}")
        self._threshold = distress_threshold
        self._policy = policy or FundamentalGatePolicy()

    def evaluate(self, context: GateContext) -> GateResult:
        if context.piotroski_f_score is None:
            triggered = self._policy.missing_data_action == "block"
            return GateResult(
                triggered=triggered,
                reason="no fundamental data — gate blocked" if triggered else "no fundamental data — gate skipped",
                confidence=self._policy.missing_data_confidence,
            )
        if context.piotroski_f_score <= self._threshold:
            return GateResult(
                triggered=True,
                reason=(
                    f"Fundamental distress: F-score {context.piotroski_f_score}"
                    f" ≤ {self._threshold} (value trap risk)"
                ),
                confidence=self._policy.triggered_confidence,
            )
        return GateResult(
            triggered=False,
            reason=f"F-score {context.piotroski_f_score} > {self._threshold} (fundamental gate passes)",
            confidence=self._policy.pass_confidence,
        )
